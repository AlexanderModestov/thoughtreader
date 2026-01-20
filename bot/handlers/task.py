import uuid
from datetime import date

from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message

from bot.database import supabase
from bot.keyboards import confirm_keyboard, tasks_list_keyboard
from bot.services.structuring import structure

router = Router()

# Temporary storage for pending tasks
pending_tasks: dict[str, dict] = {}


class TaskStates(StatesGroup):
    waiting_for_task_input = State()


def detect_project(text: str, projects: list[dict]) -> dict | None:
    """Simple keyword matching for project detection."""
    text_lower = text.lower()

    for project in projects:
        if not project.get("keywords"):
            continue
        keywords = [k.strip() for k in project["keywords"].split(",")]
        for keyword in keywords:
            if keyword and keyword.lower() in text_lower:
                return project

    return None  # Will go to "Inbox"


def get_user_projects(user_id: int) -> list[dict]:
    """Get all projects for user."""
    result = supabase.table("tr_projects").select("*").eq("user_id", user_id).order("is_default", desc=True).order("name").execute()
    return result.data


@router.message(Command("task"))
async def handle_command(message: Message, state: FSMContext):
    """Handle /task command - wait for voice or text."""
    await state.set_state(TaskStates.waiting_for_task_input)
    await message.answer("Send a voice message or text with tasks")


async def get_tasks_data(user_id: int) -> tuple[list[dict], list[dict]]:
    """Get pending and completed today tasks for user."""
    # Get pending tasks
    tasks_result = supabase.table("tr_tasks").select("*").eq("user_id", user_id).eq("is_done", False).order("due_date", nullsfirst=False).order("created_at", desc=True).limit(20).execute()
    tasks = tasks_result.data

    # Get completed today
    today = date.today().isoformat()
    done_result = supabase.table("tr_tasks").select("*").eq("user_id", user_id).eq("is_done", True).gte("created_at", today).execute()
    done_tasks = done_result.data

    return tasks, done_tasks


def format_tasks_text(tasks: list[dict], done_tasks: list[dict]) -> str:
    """Format tasks list as text."""
    priority_emoji = {"urgent": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}
    lines = ["*Your tasks*\n"]

    # Urgent tasks
    urgent = [t for t in tasks if t.get("priority") == "urgent"]
    if urgent:
        lines.append("*Urgent:*")
        for t in urgent:
            due = f" - {t['due_date']}" if t.get("due_date") else ""
            lines.append(f"🔴 {t['title']}{due}")
        lines.append("")

    # Other tasks
    other = [t for t in tasks if t.get("priority") != "urgent"]
    if other:
        for t in other:
            due = f" - {t['due_date']}" if t.get("due_date") else ""
            lines.append(f"{t['title']}{due}")
        lines.append("")

    # Completed today
    if done_tasks:
        for t in done_tasks:
            lines.append(f"~{t['title']}~")
        lines.append("")
        lines.append(f"*Completed today:* {len(done_tasks)}")

    return "\n".join(lines)


@router.message(Command("tasks"))
async def handle_list(message: Message):
    """Handle /tasks command - show task list."""
    telegram_user = message.from_user

    # Get user
    result = supabase.table("tr_users").select("*").eq("telegram_id", telegram_user.id).execute()

    if not result.data:
        await message.answer("Please start the bot with /start first.")
        return

    user = result.data[0]
    tasks, done_tasks = await get_tasks_data(user["id"])

    if not tasks and not done_tasks:
        await message.answer("No tasks yet. Use /task to create one!")
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

    # Get user
    user_result = supabase.table("tr_users").select("*").eq("telegram_id", user_id).execute()

    if not user_result.data:
        await message.answer("Please start the bot with /start first.")
        return

    user = user_result.data[0]
    projects = get_user_projects(user["id"])
    default_project = next((p for p in projects if p.get("is_default")), None)

    tasks_data = []
    for task in result:
        project = detect_project(task.get("title", ""), projects) or default_project
        task["project_name"] = project["name"] if project else "Inbox"
        task["project_id"] = project["id"] if project else None
        task["user_id"] = user["id"]
        tasks_data.append(task)

    # Store temporarily
    batch_id = str(uuid.uuid4())[:8]
    pending_tasks[batch_id] = {
        "tasks": tasks_data,
        "raw_text": text,
        "voice_file_id": voice_file_id
    }

    # Format response
    lines = [f"*Found {len(tasks_data)} tasks:*\n"]

    priority_emoji = {"urgent": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}

    for i, t in enumerate(tasks_data, 1):
        emoji = priority_emoji.get(t.get("priority", "medium"), "🟡")
        due = f" | {t['due_date']}" if t.get("due_date") else ""
        lines.append(f"{i}. {t['title']}")
        lines.append(f"   {t['project_name']} | {emoji}{due}\n")

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

    for task_data in tasks_data:
        task = {
            "user_id": task_data["user_id"],
            "project_id": task_data.get("project_id"),
            "title": task_data["title"],
            "priority": task_data.get("priority", "medium"),
            "due_date": str(task_data["due_date"]) if task_data.get("due_date") else None,
            "is_done": False,
            "raw_text": raw_text,
            "voice_file_id": voice_file_id
        }
        supabase.table("tr_tasks").insert(task).execute()

    return len(tasks_data)


async def cancel_tasks(batch_id: str):
    """Cancel pending tasks."""
    pending_tasks.pop(batch_id, None)


async def toggle_task(task_id: int) -> bool:
    """Toggle task completion status."""
    # Get current task
    result = supabase.table("tr_tasks").select("is_done").eq("id", task_id).execute()
    if not result.data:
        return False

    current_status = result.data[0]["is_done"]
    new_status = not current_status

    # Update task
    supabase.table("tr_tasks").update({"is_done": new_status}).eq("id", task_id).execute()
    return new_status


async def get_task_user_id(task_id: int) -> int | None:
    """Get user_id by task_id."""
    result = supabase.table("tr_tasks").select("user_id").eq("id", task_id).execute()
    return result.data[0]["user_id"] if result.data else None
