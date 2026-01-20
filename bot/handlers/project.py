from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message

from bot.database import supabase
from bot.keyboards import projects_keyboard

router = Router()


class ProjectStates(StatesGroup):
    waiting_for_project_input = State()


def get_user_projects(user_id: int) -> list[dict]:
    """Get all projects for user."""
    result = supabase.table("tr_projects").select("*").eq("user_id", user_id).order("is_default", desc=True).order("name").execute()
    return result.data


@router.message(Command("projects"))
async def handle_list(message: Message):
    """Handle /projects command."""
    telegram_user = message.from_user

    # Get user
    result = supabase.table("tr_users").select("*").eq("telegram_id", telegram_user.id).execute()

    if not result.data:
        await message.answer("Please start the bot with /start first.")
        return

    user = result.data[0]

    # Get projects
    projects = get_user_projects(user["id"])

    lines = ["*Your projects*\n"]

    for project in projects:
        # Count tasks for this project
        task_count_result = supabase.table("tr_tasks").select("id", count="exact").eq("project_id", project["id"]).eq("is_done", False).execute()
        task_count = task_count_result.count or 0

        if project.get("is_default"):
            emoji = "📥"
        else:
            emoji = "📁"

        lines.append(f"{emoji} *{project['name']}* ({task_count} tasks)")

        if project.get("keywords"):
            lines.append(f"   Keywords: {project['keywords']}\n")
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

    # Get user
    result = supabase.table("tr_users").select("*").eq("telegram_id", telegram_user.id).execute()

    if not result.data:
        await message.answer("Please start the bot with /start first.")
        return

    user = result.data[0]

    # Create project
    supabase.table("tr_projects").insert({
        "user_id": user["id"],
        "name": name,
        "keywords": keywords,
        "is_default": False
    }).execute()

    await state.clear()
    await message.answer(f"Project \"{name}\" created!")
