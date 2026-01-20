from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message
from sqlalchemy import select

from bot.database import get_session
from bot.keyboards import note_actions_keyboard
from bot.models import Note, Project, User
from bot.services.structuring import structure

router = Router()


class NoteStates(StatesGroup):
    waiting_for_note_input = State()


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

    return None


async def get_user_projects(db, user_id: int) -> list[Project]:
    """Get all projects for user."""
    result = await db.execute(
        select(Project).where(Project.user_id == user_id).order_by(Project.is_default.desc(), Project.name)
    )
    return list(result.scalars().all())


@router.message(Command("note"))
async def handle_command(message: Message, state: FSMContext):
    """Handle /note command - wait for voice or text."""
    await state.set_state(NoteStates.waiting_for_note_input)
    await message.answer("Send a voice message or text for the note")


@router.message(Command("notes"))
async def handle_list(message: Message):
    """Handle /notes command - show all notes."""
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

        # Get all notes
        notes_result = await db.execute(
            select(Note)
            .where(Note.user_id == user.id)
            .order_by(Note.created_at.desc())
            .limit(20)
        )
        notes = list(notes_result.scalars().all())

        if not notes:
            await message.answer("Заметок пока нет. Отправьте голосовое или текст!")
            return

        lines = ["*Ваши заметки:*\n"]

        for n in notes:
            date_str = n.created_at.strftime("%d.%m.%Y")
            title = n.title if n.title else n.content[:50] + "..."
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

        # Detect project from content
        content = result.get("content", text)
        project = detect_project(content, projects) or default_project

        # Create note
        note = Note(
            user_id=user.id,
            project_id=project.id if project else None,
            title=result.get("title"),
            content=content,
            tags=", ".join(result.get("tags", [])),
            raw_transcript=text,
            voice_file_id=voice_file_id,
            voice_duration=voice_duration
        )
        db.add(note)
        await db.commit()
        await db.refresh(note)

        # Format response
        tags = result.get("tags", [])
        tags_str = " ".join(f"#{tag}" for tag in tags) if tags else "No tags"
        project_name = project.name if project else "Inbox"

        response = (
            f"📝 *Note saved*\n\n"
            f"{content}\n\n"
            f"🏷 Tags: {tags_str}\n"
            f"📁 Project: {project_name}"
        )

        await state.clear()
        await message.answer(
            response,
            reply_markup=note_actions_keyboard(note.id, has_voice=bool(voice_file_id))
        )


async def get_note(note_id: int) -> Note | None:
    """Get note by ID."""
    async with get_session() as db:
        return await db.get(Note, note_id)


async def delete_note(note_id: int) -> bool:
    """Delete note by ID."""
    async with get_session() as db:
        note = await db.get(Note, note_id)
        if note:
            await db.delete(note)
            await db.commit()
            return True
    return False
