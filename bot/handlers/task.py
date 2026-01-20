import uuid
from datetime import date

from aiogram import Bot, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message
from sqlalchemy import select

from bot.database import get_session
from bot.keyboards import confirm_keyboard, tasks_list_keyboard
from bot.models import Project, Task, User
from bot.services.structuring import structure

router = Router()

# Temporary storage for pending tasks
pending_tasks: dict[str, dict] = {}


class TaskStates(StatesGroup):
    waiting_for_task_input = State()


def detect_project(text: str, projects: list[Project]) -> Project | None:
    """Simple keyword matching for project detection."""
    text_lower = text.lower()

    for project in projects:
        if not project.keywords:
            continue
        keywords = [k.strip() for k in project.keywords.split(",")]
        for keyword in keywords:
            if keyword and keyword.lower() in text_lower:
                return project

    return None  # Will go to "Inbox"


async def get_user_projects(db, user_id: int) -> list[Project]:
    """Get all projects for user."""
    result = await db.execute(
        select(Project).where(Project.user_id == user_id).order_by(Project.is_default.desc(), Project.name)
    )
    return list(result.scalars().all())


@router.message(Command("task"))
async def handle_command(message: Message, state: FSMContext):
    """Handle /task command - wait for voice or text."""
    await state.set_state(TaskStates.waiting_for_task_input)
    await message.answer("Send a voice message or text with tasks")


async def get_tasks_data(user_id: int) -> tuple[list[Task], list[Task]]:
    """Get pending and completed today tasks for user."""
    async with get_session() as db:
        # Get pending tasks
        tasks_result = await db.execute(
            select(Task)
            .where(Task.user_id == user_id)
            .where(Task.is_done == False)
            .order_by(Task.due_date.asc().nullslast(), Task.created_at.desc())
            .limit(20)
        )
        tasks = list(tasks_result.scalars().all())

        # Get completed today
        today = date.today()
        done_result = await db.execute(
            select(Task)
            .where(Task.user_id == user_id)
            .where(Task.is_done == True)
        )
        done_tasks = [t for t in done_result.scalars() if t.created_at.date() == today]

        return tasks, done_tasks


def format_tasks_text(tasks: list[Task], done_tasks: list[Task]) -> str:
    """Format tasks list as text."""
    priority_emoji = {"urgent": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}
    lines = ["📋 *Ваши задачи*\n"]

    # Urgent tasks
    urgent = [t for t in tasks if t.priority == "urgent"]
    if urgent:
        lines.append("*Срочные:*")
        for t in urgent:
            due = f" — {t.due_date}" if t.due_date else ""
            lines.append(f"🔴 ☐ {t.title}{due}")
        lines.append("")

    # Other tasks
    other = [t for t in tasks if t.priority != "urgent"]
    if other:
        for t in other:
            due = f" — {t.due_date}" if t.due_date else ""
            lines.append(f"☐ {t.title}{due}")
        lines.append("")

    # Completed today
    if done_tasks:
        for t in done_tasks:
            lines.append(f"~{t.title}~")
        lines.append("")
        lines.append(f"✅ *Выполнено сегодня:* {len(done_tasks)}")

    return "\n".join(lines)


@router.message(Command("tasks"))
async def handle_list(message: Message):
    """Handle /tasks command - show task list."""
    telegram_user = message.from_user

    async with get_session() as db:
        # Get user
        result = await db.execute(
            select(User).where(User.telegram_id == telegram_user.id)
        )
        user = result.scalar()

        if not user:
            await message.answer("Please start the bot with /start first.")
            return

        tasks, done_tasks = await get_tasks_data(user.id)

        if not tasks and not done_tasks:
            await message.answer("📋 Задач пока нет. Используйте /task для создания!")
            return

        text = format_tasks_text(tasks, done_tasks)
        keyboard = tasks_list_keyboard(tasks) if tasks else None

        await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")


async def process_tasks(message: Message, text: str, user_id: int, state: FSMContext, voice_file_id: str = None):
    """Process text as tasks."""
    # Structure via Claude
    try:
        result = await structure(text, "tasks")
    except Exception as e:
        await message.answer(f"Error processing tasks: {str(e)}")
        return

    if not result:
        await message.answer("No tasks found in the message.")
        return

    # Get user and projects
    async with get_session() as db:
        user_result = await db.execute(
            select(User).where(User.telegram_id == user_id)
        )
        user = user_result.scalar()

        if not user:
            await message.answer("Please start the bot with /start first.")
            return

        projects = await get_user_projects(db, user.id)
        default_project = next((p for p in projects if p.is_default), None)

        tasks_data = []
        for task in result:
            project = detect_project(task.get("title", ""), projects) or default_project
            task["project_name"] = project.name if project else "Inbox"
            task["project_id"] = project.id if project else None
            task["user_id"] = user.id
            tasks_data.append(task)

    # Store temporarily
    batch_id = str(uuid.uuid4())[:8]
    pending_tasks[batch_id] = {
        "tasks": tasks_data,
        "raw_text": text,
        "voice_file_id": voice_file_id
    }

    # Format response
    lines = [f"✅ *Found {len(tasks_data)} tasks:*\n"]

    priority_emoji = {"urgent": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}

    for i, t in enumerate(tasks_data, 1):
        emoji = priority_emoji.get(t.get("priority", "medium"), "🟡")
        due = f" · 📅 {t['due_date']}" if t.get("due_date") else ""
        lines.append(f"{i}. ☐ {t['title']}")
        lines.append(f"   📁 {t['project_name']} · {emoji}{due}\n")

    await state.clear()
    await message.answer(
        "\n".join(lines),
        reply_markup=confirm_keyboard("tasks", batch_id)
    )


async def save_tasks(batch_id: str) -> int:
    """Save tasks from pending to database."""
    if batch_id not in pending_tasks:
        return 0

    batch = pending_tasks.pop(batch_id)
    tasks_data = batch["tasks"]
    raw_text = batch.get("raw_text")
    voice_file_id = batch.get("voice_file_id")

    async with get_session() as db:
        for task_data in tasks_data:
            task = Task(
                user_id=task_data["user_id"],
                project_id=task_data.get("project_id"),
                title=task_data["title"],
                priority=task_data.get("priority", "medium"),
                due_date=task_data.get("due_date"),
                raw_text=raw_text,
                voice_file_id=voice_file_id
            )
            db.add(task)
        await db.commit()

    return len(tasks_data)


async def cancel_tasks(batch_id: str):
    """Cancel pending tasks."""
    pending_tasks.pop(batch_id, None)


async def toggle_task(task_id: int) -> bool:
    """Toggle task completion status."""
    async with get_session() as db:
        task = await db.get(Task, task_id)
        if task:
            task.is_done = not task.is_done
            await db.commit()
            return task.is_done
    return False


async def get_task_user_id(task_id: int) -> int | None:
    """Get user_id by task_id."""
    async with get_session() as db:
        task = await db.get(Task, task_id)
        return task.user_id if task else None
