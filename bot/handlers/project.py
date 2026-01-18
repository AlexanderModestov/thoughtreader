from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message
from sqlalchemy import func, select

from bot.database import get_session
from bot.keyboards import projects_keyboard
from bot.models import Project, Task, User

router = Router()


class ProjectStates(StatesGroup):
    waiting_for_project_input = State()


async def get_user_projects(db, user_id: int) -> list[Project]:
    """Get all projects for user."""
    result = await db.execute(
        select(Project).where(Project.user_id == user_id).order_by(Project.is_default.desc(), Project.name)
    )
    return list(result.scalars().all())


@router.message(Command("projects"))
async def handle_list(message: Message):
    """Handle /projects command."""
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

        # Get projects with task counts
        projects = await get_user_projects(db, user.id)

        lines = ["📁 *Your projects*\n"]

        for project in projects:
            # Count tasks for this project
            task_count_result = await db.execute(
                select(func.count(Task.id))
                .where(Task.project_id == project.id)
                .where(Task.is_done == False)
            )
            task_count = task_count_result.scalar() or 0

            if project.is_default:
                emoji = "📥"
            else:
                emoji = "📁"

            lines.append(f"{emoji} *{project.name}* ({task_count} tasks)")

            if project.keywords:
                lines.append(f"   Keywords: {project.keywords}\n")
            else:
                lines.append("")

        await message.answer(
            "\n".join(lines),
            reply_markup=projects_keyboard()
        )


async def start_new_project(message: Message, state: FSMContext):
    """Start new project creation flow."""
    await state.set_state(ProjectStates.waiting_for_project_input)
    await message.answer(
        "Write the name and keywords separated by |\n"
        "Example: Repair | repair, apartment, master"
    )


@router.message(ProjectStates.waiting_for_project_input)
async def process_new_project(message: Message, state: FSMContext):
    """Process new project creation from text."""
    telegram_user = message.from_user
    text = message.text

    # Parse input
    parts = text.split("|")
    name = parts[0].strip()
    keywords = parts[1].strip() if len(parts) > 1 else ""

    if not name:
        await message.answer("Please provide a project name.")
        return

    async with get_session() as db:
        # Get user
        result = await db.execute(
            select(User).where(User.telegram_id == telegram_user.id)
        )
        user = result.scalar()

        if not user:
            await message.answer("Please start the bot with /start first.")
            return

        # Create project
        project = Project(
            user_id=user.id,
            name=name,
            keywords=keywords,
            is_default=False
        )
        db.add(project)
        await db.commit()

    await state.clear()
    await message.answer(f"✅ Project \"{name}\" created!")
