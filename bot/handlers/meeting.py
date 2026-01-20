import logging
import uuid

from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message
from sqlalchemy import select

from bot.database import get_session
from bot.keyboards import confirm_keyboard, meeting_actions_keyboard
from bot.models import Meeting, User
from bot.services.structuring import structure

logger = logging.getLogger(__name__)

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

    async with get_session() as db:
        # Get user
        result = await db.execute(
            select(User).where(User.telegram_id == telegram_user.id)
        )
        user = result.scalar()

        if not user:
            await message.answer("Please start the bot with /start first.")
            return

        # Get all meetings
        meetings_result = await db.execute(
            select(Meeting)
            .where(Meeting.user_id == user.id)
            .order_by(Meeting.created_at.desc())
            .limit(20)
        )
        meetings = list(meetings_result.scalars().all())

        if not meetings:
            await message.answer("No meetings yet. Use /meet to create one!")
            return

        lines = ["*Your meetings:*\n"]

        for m in meetings:
            participants = m.participants if m.participants else "Not specified"
            date_str = m.created_at.strftime("%d.%m.%Y")
            lines.append(f"*{m.title}*")
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
    async with get_session() as db:
        user_result = await db.execute(
            select(User).where(User.telegram_id == user_id)
        )
        user = user_result.scalar()

        if not user:
            await message.answer("Please start the bot with /start first.")
            return

    # Store temporarily
    batch_id = str(uuid.uuid4())[:8]
    pending_meetings[batch_id] = {
        "user_id": user.id,
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
        f"📋 *{result.get('title', 'Meeting')}*\n\n"
        f"👥 *Participants:* {participants_str}\n\n"
        f"📝 *Agenda:*\n{agenda_str}\n\n"
        f"🎯 *Goal:* {goal_str}"
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

    async with get_session() as db:
        meeting = Meeting(
            user_id=data["user_id"],
            title=data["title"],
            participants=", ".join(data["participants"]),
            agenda="\n".join(f"- {item}" for item in data["agenda"]),
            goal=data.get("goal"),
            scheduled_at=data.get("scheduled_at"),
            raw_transcript=data.get("raw_transcript"),
            voice_file_id=data.get("voice_file_id"),
            voice_duration=data.get("voice_duration")
        )
        db.add(meeting)
        await db.commit()
        await db.refresh(meeting)
        return meeting.id


async def cancel_meeting(batch_id: str):
    """Cancel pending meeting."""
    pending_meetings.pop(batch_id, None)


async def get_meeting(meeting_id: int) -> Meeting | None:
    """Get meeting by ID."""
    async with get_session() as db:
        return await db.get(Meeting, meeting_id)


async def delete_meeting(meeting_id: int) -> bool:
    """Delete meeting by ID."""
    async with get_session() as db:
        meeting = await db.get(Meeting, meeting_id)
        if meeting:
            await db.delete(meeting)
            await db.commit()
            return True
    return False
