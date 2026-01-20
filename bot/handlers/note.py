from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message

from bot.database import supabase
from bot.keyboards import note_actions_keyboard
from bot.services.structuring import structure

router = Router()


class NoteStates(StatesGroup):
    waiting_for_note_input = State()


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

    return None


def get_user_projects(user_id: int) -> list[dict]:
    """Get all projects for user."""
    result = supabase.table("tr_projects").select("*").eq("user_id", user_id).order("is_default", desc=True).order("name").execute()
    return result.data


@router.message(Command("note"))
async def handle_command(message: Message, state: FSMContext):
    """Handle /note command - wait for voice or text."""
    await state.set_state(NoteStates.waiting_for_note_input)
    await message.answer("Send a voice message or text for the note")


@router.message(Command("notes"))
async def handle_list(message: Message):
    """Handle /notes command - show all notes."""
    telegram_user = message.from_user

    # Get user
    result = supabase.table("tr_users").select("*").eq("telegram_id", telegram_user.id).execute()

    if not result.data:
        await message.answer("Please start the bot with /start first.")
        return

    user = result.data[0]

    # Get all notes
    notes_result = supabase.table("tr_notes").select("*").eq("user_id", user["id"]).order("created_at", desc=True).limit(20).execute()
    notes = notes_result.data

    if not notes:
        await message.answer("No notes yet. Send a voice or text message!")
        return

    lines = ["*Your notes:*\n"]

    for n in notes:
        date_str = n["created_at"][:10]  # YYYY-MM-DD
        title = n.get("title") or (n["content"][:50] + "..." if len(n["content"]) > 50 else n["content"])
        lines.append(f"*{title}*")
        lines.append(f"   {date_str}\n")

    await message.answer("\n".join(lines), parse_mode="Markdown")


async def process_note(message: Message, text: str, user_id: int, state: FSMContext, voice_file_id: str = None, voice_duration: int = None):
    """Process text as a note and save immediately."""
    # Structure via Claude
    try:
        result = await structure(text, "note")
    except Exception as e:
        await message.answer(f"Error processing note: {str(e)}")
        return

    # Get user
    user_result = supabase.table("tr_users").select("*").eq("telegram_id", user_id).execute()

    if not user_result.data:
        await message.answer("Please start the bot with /start first.")
        return

    user = user_result.data[0]
    projects = get_user_projects(user["id"])
    default_project = next((p for p in projects if p.get("is_default")), None)

    # Detect project from content
    content = result.get("content", text)
    project = detect_project(content, projects) or default_project

    # Create note
    note_data = {
        "user_id": user["id"],
        "project_id": project["id"] if project else None,
        "title": result.get("title"),
        "content": content,
        "tags": ", ".join(result.get("tags", [])),
        "raw_transcript": text,
        "voice_file_id": voice_file_id,
        "voice_duration": voice_duration
    }
    note_result = supabase.table("tr_notes").insert(note_data).execute()
    note = note_result.data[0]

    # Format response
    tags = result.get("tags", [])
    tags_str = " ".join(f"#{tag}" for tag in tags) if tags else "No tags"
    project_name = project["name"] if project else "Inbox"

    response = (
        f"*Note saved*\n\n"
        f"{content}\n\n"
        f"Tags: {tags_str}\n"
        f"Project: {project_name}"
    )

    await state.clear()
    await message.answer(
        response,
        reply_markup=note_actions_keyboard(note["id"], has_voice=bool(voice_file_id))
    )


async def get_note(note_id: int) -> dict | None:
    """Get note by ID."""
    result = supabase.table("tr_notes").select("*").eq("id", note_id).execute()
    return result.data[0] if result.data else None


async def delete_note(note_id: int) -> bool:
    """Delete note by ID."""
    result = supabase.table("tr_notes").delete().eq("id", note_id).execute()
    return len(result.data) > 0 if result.data else False
