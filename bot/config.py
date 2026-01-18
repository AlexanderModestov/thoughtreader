from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Telegram
    telegram_bot_token: str

    # Anthropic (Claude)
    anthropic_api_key: str
    anthropic_model: str = "claude-3-5-sonnet-latest"

    # OpenAI (Whisper)
    openai_api_key: str
    whisper_model: str = "whisper-1"
    whisper_language: str = "ru"

    # Database
    database_url: str = "sqlite+aiosqlite:///./data/bot.db"

    # Structuring settings
    max_tokens: int = 2000

    class Config:
        env_file = ".env"


settings = Settings()
