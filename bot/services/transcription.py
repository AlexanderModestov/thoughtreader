from io import BytesIO

from openai import AsyncOpenAI

from bot.config import settings

# Reusable client instance
_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI:
    """Get or create OpenAI client."""
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=settings.openai_api_key)
    return _client


async def transcribe(audio_bytes: bytes) -> str:
    """Transcribe audio bytes using OpenAI Whisper API."""
    client = _get_client()

    audio_file = BytesIO(audio_bytes)
    audio_file.name = "voice.ogg"

    response = await client.audio.transcriptions.create(
        model=settings.whisper_model,
        file=audio_file,
        language=settings.whisper_language
    )

    return response.text
