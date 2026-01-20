import uuid

from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message

from bot.database import supabase
from bot.keyboards import confirm_keyboard, meeting_actions_keyboard
from bot.services.structuring import structure

router = Router()

# Temporary storage for pending meetings
pending_meetings: dict[str, dict] = {}


class MeetingStates(StatesGroup):
    waiting_for_meeting_input = State()


@router.message(Command("meet"))
async def handle_command(message: Message, state: FSMContext):
    """Handle /meet command - wait for voice or text."""
    await state.set_state(MeetingStates.waiting_for_meeting_input)
    await message.answer("Send a voice message or text about the meeting")


@router.message(Command("meetings"))
async def handle_list(message: Message):
    """Handle /meetings command - show all meetings."""
    telegram_user = message.from_user

    # Get user
    result = supabase.table("tr_users").select("*").eq("telegram_id", telegram_user.id).execute()

    if not result.data:
        await message.answer("Please start the bot with /start first.")
        return

    user = result.data[0]

    # Get all meetings
    meetings_result = supabase.table("tr_meetings").select("*").eq("user_id", user["id"]).order("created_at", desc=True).limit(20).execute()
    meetings = meetings_result.data

    if not meetings:
        await message.answer("No meetings yet. Use /meet to create one!")
        return

    lines = ["*Your meetings:*\n"]

    for m in meetings:
        participants = m.get("participants") or "Not specified"
        date_str = m["created_at"][:10]  # YYYY-MM-DD
        lines.append(f"*{m['title']}*")
        lines.append(f"   Participants: {participants}")
        lines.append(f"   Created: {date_str}\n")

    await message.answer("\n".join(lines), parse_mode="Markdown")


async def process_meeting(message: Message, text: str, user_id: int, state: FSMContext, voice_file_id: str = None, voice_duration: int = None):
    """Process text as a meeting."""
    # Structure via Claude
    try:
        result = await structure(text, "meeting")
    except Exception as e:
        await message.answer(f"Error processing meeting: {str(e)}")
        return

    # Get user
    user_result = supabase.table("tr_users").select("*").eq("telegram_id", user_id).execute()

    if not user_result.data:
        await message.answer("Please start the bot with /start first.")
        return

    user = user_result.data[0]

    # Store temporarily
    batch_id = str(uuid.uuid4())[:8]
    pending_meetings[batch_id] = {
        "user_id": user["id"],
        "title": result.get("title", "Meeting"),
        "participants": result.get("participants", []),
        "agenda": result.get("agenda", []),
        "goal": result.get("goal"),
        "raw_transcript": text,
        "voice_file_id": voice_file_id,
        "voice_duration": voice_duration
    }

    # Format response
    participants_str = ", ".join(result.get("participants", [])) or "Not specified"
    agenda_items = result.get("agenda", [])
    agenda_str = "\n".join(f"{i}. {item}" for i, item in enumerate(agenda_items, 1)) or "Not specified"
    goal_str = result.get("goal") or "Not specified"

    response = (
        f"*{result.get('title', 'Meeting')}*\n\n"
        f"*Participants:* {participants_str}\n\n"
        f"*Agenda:*\n{agenda_str}\n\n"
        f"*Goal:* {goal_str}"
    )

    await state.clear()
    await message.answer(
        response,
        reply_markup=confirm_keyboard("meeting", batch_id)
    )


async def save_meeting(batch_id: str) -> int | None:
    """Save meeting from pending to database.

    Returns meeting_id or None.
    """
    if batch_id not in pending_meetings:
        return None

    data = pending_meetings.pop(batch_id)

    meeting_data = {
        "user_id": data["user_id"],
        "title": data["title"],
        "participants": ", ".join(data["participants"]),
        "agenda": "\n".join(f"- {item}" for item in data["agenda"]),
        "goal": data.get("goal"),
        "scheduled_at": data.get("scheduled_at"),
        "raw_transcript": data.get("raw_transcript"),
        "voice_file_id": data.get("voice_file_id"),
        "voice_duration": data.get("voice_duration")
    }
    result = supabase.table("tr_meetings").insert(meeting_data).execute()
    return result.data[0]["id"] if result.data else None


async def cancel_meeting(batch_id: str):
    """Cancel pending meeting."""
    pending_meetings.pop(batch_id, None)


async def get_meeting(meeting_id: int) -> dict | None:
    """Get meeting by ID."""
    result = supabase.table("tr_meetings").select("*").eq("id", meeting_id).execute()
    return result.data[0] if result.data else None


async def delete_meeting(meeting_id: int) -> bool:
    """Delete meeting by ID."""
    result = supabase.table("tr_meetings").delete().eq("id", meeting_id).execute()
    return len(result.data) > 0 if result.data else False
