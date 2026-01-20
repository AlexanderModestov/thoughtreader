from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from bot.database import supabase
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

    # Get user
    user_result = supabase.table("tr_users").select("*").eq("telegram_id", telegram_user.id).execute()

    if not user_result.data:
        await message.answer("Please start the bot with /start first.")
        return

    user = user_result.data[0]

    # Perform search
    results = search_service(user["id"], query)

    if not results:
        await message.answer(f"Nothing found for \"{query}\"")
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

    lines = [f"*Found: {len(results)}*\n"]

    for r in results:
        emoji = type_emoji.get(r["entity_type"], "📄")
        tname = type_name.get(r["entity_type"], "item")
        date_str = r["created_at"][:10]  # YYYY-MM-DD

        status = ""
        if r["entity_type"] == "task" and r.get("is_done"):
            status = " ✓"

        lines.append(f"{emoji} {r['title']}{status} ({tname}, {date_str})")

    lines.append("\nSend another query or use /search <query>")

    await message.answer("\n".join(lines))
