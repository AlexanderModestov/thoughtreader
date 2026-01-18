from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from bot.handlers import meeting, note, task
from bot.handlers.meeting import MeetingStates
from bot.handlers.note import NoteStates
from bot.handlers.task import TaskStates
from bot.keyboards import intent_keyboard
from bot.services.transcription import transcribe

router = Router()

# Temporary storage for transcriptions (in memory)
pending_transcripts: dict[int, dict] = {}


@router.message(F.voice)
async def handle_voice(message: Message, state: FSMContext, bot: Bot):
    """Handle voice message - either process with awaiting type or ask."""
    user_id = message.from_user.id
    voice = message.voice

    # Download file
    file = await bot.get_file(voice.file_id)
    audio_bytes = await bot.download_file(file.file_path)

    # Show processing message
    processing_msg = await message.answer("🎙 Processing...")

    # Transcribe
    try:
        text = await transcribe(audio_bytes.read())
    except Exception as e:
        await processing_msg.edit_text(f"Error transcribing: {str(e)}")
        return

    # Delete processing message
    await processing_msg.delete()

    # Check if we're awaiting a specific type
    current_state = await state.get_state()

    if current_state == TaskStates.waiting_for_task_input:
        await task.process_tasks(message, text, user_id, state, voice.file_id)
    elif current_state == MeetingStates.waiting_for_meeting_input:
        await meeting.process_meeting(message, text, user_id, state, voice.file_id, voice.duration)
    elif current_state == NoteStates.waiting_for_note_input:
        await note.process_note(message, text, user_id, state, voice.file_id, voice.duration)
    else:
        # Store for later processing
        pending_transcripts[user_id] = {
            "text": text,
            "voice_file_id": voice.file_id,
            "voice_duration": voice.duration
        }

        # Show preview and ask
        preview = text[:100] + "..." if len(text) > 100 else text
        await message.answer(
            f"🎙 *Transcribed:*\n_{preview}_\n\nWhat to do?",
            reply_markup=intent_keyboard()
        )


@router.message(F.text)
async def handle_text(message: Message, state: FSMContext):
    """Handle text message - process with awaiting type."""
    user_id = message.from_user.id
    text = message.text

    # Check if we're awaiting a specific type
    current_state = await state.get_state()

    if current_state == TaskStates.waiting_for_task_input:
        await task.process_tasks(message, text, user_id, state)
    elif current_state == MeetingStates.waiting_for_meeting_input:
        await meeting.process_meeting(message, text, user_id, state)
    elif current_state == NoteStates.waiting_for_note_input:
        await note.process_note(message, text, user_id, state)
    else:
        # Unknown text - suggest commands
        await message.answer(
            "Send a command first:\n"
            "• /task — create tasks\n"
            "• /meet — create a meeting\n"
            "• /note — save a note\n\n"
            "Or just send a voice message."
        )


async def process_pending_transcript(user_id: int, intent: str, message: Message, state: FSMContext) -> bool:
    """Process pending transcript with selected intent."""
    if user_id not in pending_transcripts:
        return False

    data = pending_transcripts.pop(user_id)
    text = data["text"]
    voice_file_id = data.get("voice_file_id")
    voice_duration = data.get("voice_duration")

    if intent == "tasks":
        await task.process_tasks(message, text, user_id, state, voice_file_id)
    elif intent == "meeting":
        await meeting.process_meeting(message, text, user_id, state, voice_file_id, voice_duration)
    elif intent == "note":
        await note.process_note(message, text, user_id, state, voice_file_id, voice_duration)

    return True
