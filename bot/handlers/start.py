from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy import select

from bot.database import get_session
from bot.models import Project, User

router = Router()


@router.message(Command("start", "help"))
async def handle_start(message: Message):
    """Handle /start and /help commands."""
    user = message.from_user

    async with get_session() as db:
        # Check if user exists
        result = await db.execute(
            select(User).where(User.telegram_id == user.id)
        )
        existing = result.scalar()

        if not existing:
            # Create new user
            new_user = User(telegram_id=user.id, username=user.username)
            db.add(new_user)
            await db.flush()

            # Create default "Inbox" project
            inbox = Project(
                user_id=new_user.id,
                name="Inbox",
                is_default=True
            )
            db.add(inbox)
            await db.commit()

    await message.answer(
        "👋 *Hi! I'm Thought Assistant*\n\n"
        "Send me a voice message or text:\n"
        "• `/task` — create tasks\n"
        "• `/meet` — create a meeting\n"
        "• `/note` — save a note\n\n"
        "Or just send a voice message — I'll ask what to do with it.\n\n"
        "/projects — your projects\n"
        "/tasks — your tasks\n"
        "/search — search"
    )
