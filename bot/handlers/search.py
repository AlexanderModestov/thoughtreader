from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message
from sqlalchemy import select

from bot.database import get_session
from bot.models import User
from bot.services.search import search as search_service

router = Router()


@router.message(Command("search"))
async def handle_search(message: Message, command: CommandObject):
    """Handle /search command."""
    telegram_user = message.from_user

    # Get search query from command arguments
    if command.args:
        query = command.args
    else:
        await message.answer("Usage: /search <query>\nExample: /search Q3")
        return

    async with get_session() as db:
        # Get user
        user_result = await db.execute(
            select(User).where(User.telegram_id == telegram_user.id)
        )
        user = user_result.scalar()

        if not user:
            await message.answer("Please start the bot with /start first.")
            return

        # Perform search
        results = await search_service(user.id, query, db)

        if not results:
            await message.answer(f"🔍 Nothing found for \"{query}\"")
            return

        # Format results
        type_emoji = {
            "task": "✅",
            "note": "📝",
            "meeting": "📋"
        }
        type_name = {
            "task": "task",
            "note": "note",
            "meeting": "meeting"
        }

        lines = [f"🔍 *Found: {len(results)}*\n"]

        for r in results:
            emoji = type_emoji.get(r.entity_type, "📄")
            tname = type_name.get(r.entity_type, "item")
            date_str = r.created_at.strftime("%d.%m")

            status = ""
            if r.entity_type == "task" and r.is_done:
                status = " ✓"

            lines.append(f"{emoji} {r.title}{status} ({tname}, {date_str})")

        lines.append("\nSend another query or use /search <query>")

        await message.answer("\n".join(lines))
