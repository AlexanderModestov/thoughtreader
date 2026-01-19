from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy import select

from bot.database import get_session
from bot.handlers.meeting import MeetingStates
from bot.handlers.note import NoteStates
from bot.handlers.task import TaskStates
from bot.handlers import meeting, note, task
from bot.keyboards import open_note_keyboard
from bot.models import Meeting, Note, Project, Task, User
from bot.services.extraction import extract_from_message
from bot.services.formatter import format_extraction_response
from bot.services.transcription import transcribe

router = Router()


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


async def process_auto_extraction(message: Message, text: str, user_id: int, voice_file_id: str = None, voice_duration: int = None):
    """Process message with auto-extraction: extract tasks, meetings, save note."""
    # Extract using Claude
    try:
        result = await extract_from_message(text)
    except Exception as e:
        await message.answer(f"Error processing: {str(e)}")
        return

    async with get_session() as db:
        # Get user
        user_result = await db.execute(
            select(User).where(User.telegram_id == user_id)
        )
        user = user_result.scalar()

        if not user:
            await message.answer("Please start the bot with /start first.")
            return

        # Get projects
        projects_result = await db.execute(
            select(Project).where(Project.user_id == user.id)
        )
        projects = list(projects_result.scalars().all())
        default_project = next((p for p in projects if p.is_default), None)

        # Create note (always)
        note_obj = Note(
            user_id=user.id,
            project_id=default_project.id if default_project else None,
            title=result.summary[:100] if result.summary else None,
            content=result.summary,
            raw_transcript=text,
            voice_file_id=voice_file_id,
            voice_duration=voice_duration
        )
        db.add(note_obj)
        await db.flush()  # Get note ID

        # Create tasks (if any)
        for extracted_task in result.tasks:
            project = detect_project(extracted_task.title, projects) or default_project
            task_obj = Task(
                user_id=user.id,
                project_id=project.id if project else None,
                source_note_id=note_obj.id,
                title=extracted_task.title,
                priority=extracted_task.priority,
                due_date=extracted_task.due_date,
                raw_text=text,
                voice_file_id=voice_file_id
            )
            db.add(task_obj)

        # Create meetings (if any)
        for extracted_meeting in result.meetings:
            meeting_obj = Meeting(
                user_id=user.id,
                source_note_id=note_obj.id,
                title=extracted_meeting.title,
                participants=", ".join(extracted_meeting.participants),
                agenda="\n".join(f"- {item}" for item in extracted_meeting.agenda),
                goal=extracted_meeting.goal,
                raw_transcript=text,
                voice_file_id=voice_file_id,
                voice_duration=voice_duration
            )
            db.add(meeting_obj)

        await db.commit()

        # Format and send response
        response = format_extraction_response(result, note_obj.id)
        await message.answer(
            response,
            reply_markup=open_note_keyboard(note_obj.id)
        )


@router.message(F.voice)
async def handle_voice(message: Message, state: FSMContext, bot: Bot):
    """Handle voice message - check state or auto-extract."""
    user_id = message.from_user.id
    voice = message.voice

    # Download and transcribe
    file = await bot.get_file(voice.file_id)
    audio_bytes = await bot.download_file(file.file_path)

    processing_msg = await message.answer("Processing...")

    try:
        text = await transcribe(audio_bytes.read())
    except Exception as e:
        await processing_msg.edit_text(f"Error transcribing: {str(e)}")
        return

    await processing_msg.delete()

    # Check if awaiting specific type (from /task, /meet, /note commands)
    current_state = await state.get_state()

    if current_state == TaskStates.waiting_for_task_input:
        await task.process_tasks(message, text, user_id, state, voice.file_id)
    elif current_state == MeetingStates.waiting_for_meeting_input:
        await meeting.process_meeting(message, text, user_id, state, voice.file_id, voice.duration)
    elif current_state == NoteStates.waiting_for_note_input:
        await note.process_note(message, text, user_id, state, voice.file_id, voice.duration)
    else:
        # Auto-extraction flow
        await process_auto_extraction(message, text, user_id, voice.file_id, voice.duration)


@router.message(F.text)
async def handle_text(message: Message, state: FSMContext):
    """Handle text message - check state or auto-extract."""
    user_id = message.from_user.id
    text = message.text

    # Skip commands
    if text.startswith("/"):
        return

    # Check if awaiting specific type
    current_state = await state.get_state()

    if current_state == TaskStates.waiting_for_task_input:
        await task.process_tasks(message, text, user_id, state)
    elif current_state == MeetingStates.waiting_for_meeting_input:
        await meeting.process_meeting(message, text, user_id, state)
    elif current_state == NoteStates.waiting_for_note_input:
        await note.process_note(message, text, user_id, state)
    else:
        # Auto-extraction flow
        await process_auto_extraction(message, text, user_id)
