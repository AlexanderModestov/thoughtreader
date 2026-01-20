from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from bot.database import supabase

router = Router()


@router.message(Command("start", "help"))
async def handle_start(message: Message):
    """Handle /start and /help commands."""
    user = message.from_user

    # Check if user exists
    result = supabase.table("tr_users").select("*").eq("telegram_id", user.id).execute()

    if not result.data:
        # Create new user
        new_user = supabase.table("tr_users").insert({
            "telegram_id": user.id,
            "username": user.username
        }).execute()

        user_id = new_user.data[0]["id"]

        # Create default "Inbox" project
        supabase.table("tr_projects").insert({
            "user_id": user_id,
            "name": "Inbox",
            "is_default": True,
            "keywords": ""
        }).execute()

    await message.answer(
        "*Hi! I'm Thought Assistant*\n\n"
        "Send me a voice message or text:\n"
        "* `/task` - create tasks\n"
        "* `/meet` - create a meeting\n"
        "* `/note` - save a note\n\n"
        "Or just send a voice message - I'll ask what to do with it.\n\n"
        "/projects - your projects\n"
        "/tasks - your tasks\n"
        "/search - search"
    )
