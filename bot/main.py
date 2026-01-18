import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from bot.config import settings
from bot.database import init_db
from bot.handlers.callbacks import router as callbacks_router
from bot.handlers.meeting import router as meeting_router
from bot.handlers.note import router as note_router
from bot.handlers.project import router as project_router
from bot.handlers.search import router as search_router
from bot.handlers.start import router as start_router
from bot.handlers.task import router as task_router
from bot.handlers.voice import router as voice_router

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)


async def main():
    """Main entry point for the bot."""
    # Initialize database
    logger.info("Initializing database...")
    await init_db()

    # Create bot and dispatcher
    bot = Bot(
        token=settings.telegram_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN)
    )
    dp = Dispatcher()

    # Include routers
    dp.include_router(start_router)
    dp.include_router(task_router)
    dp.include_router(meeting_router)
    dp.include_router(note_router)
    dp.include_router(project_router)
    dp.include_router(search_router)
    dp.include_router(voice_router)
    dp.include_router(callbacks_router)

    # Start bot
    logger.info("Starting bot...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
