import json
import logging
import re
from datetime import date

from anthropic import AsyncAnthropic

from bot.config import settings

logger = logging.getLogger(__name__)

# Reusable client instance
_client: AsyncAnthropic | None = None


def _get_client() -> AsyncAnthropic:
    """Get or create Anthropic client."""
    global _client
    if _client is None:
        _client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    return _client


PROMPT = """You are an assistant for structuring thoughts. Reply ONLY with valid JSON, no explanations or markdown.

Type: {type}
Text: {text}
Today: {today}

If type = "tasks":
Extract ALL tasks from the text. Return JSON array:
[{{"title": "task description", "priority": "low/medium/high/urgent", "due_date": "YYYY-MM-DD or null"}}]

Date rules:
- "tomorrow" -> tomorrow's date
- "on Monday" -> next Monday
- "next week" -> Monday of next week
- Not specified -> null

Priority rules:
- "urgent", "asap", "burning" -> urgent
- "important", "priority" -> high
- Default -> medium
- "someday", "not urgent" -> low

If type = "meeting":
Structure as a meeting. Return JSON object:
{{"title": "meeting title", "participants": ["name1", "name2"], "agenda": ["item1", "item2"], "goal": "meeting goal"}}

If type = "note":
Clean text from filler words, extract tags. Return JSON object:
{{"title": "short title or null", "content": "cleaned text", "tags": ["tag1", "tag2"]}}

IMPORTANT: Return ONLY the JSON, no markdown code blocks, no explanations."""


def _extract_json(text: str) -> str:
    """Extract JSON from response, handling markdown code blocks."""
    # Remove markdown code blocks if present
    text = text.strip()

    # Try to extract from ```json ... ``` or ``` ... ```
    json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', text)
    if json_match:
        return json_match.group(1).strip()

    # Return as-is if no code block found
    return text


async def structure(text: str, content_type: str) -> dict | list:
    """Structure text using Claude API."""
    client = _get_client()

    prompt_text = PROMPT.format(
        type=content_type,
        text=text,
        today=date.today().isoformat()
    )

    logger.info(f"Structuring text as '{content_type}', text length: {len(text)}")

    response = await client.messages.create(
        model=settings.anthropic_model,
        max_tokens=settings.max_tokens,
        messages=[{
            "role": "user",
            "content": prompt_text
        }]
    )

    # Get response text
    if not response.content:
        logger.error("Empty response from Claude API")
        raise ValueError("Empty response from Claude API")

    response_text = response.content[0].text
    logger.info(f"Claude response: {response_text[:200]}...")

    # Extract JSON from response
    json_text = _extract_json(response_text)

    if not json_text:
        logger.error(f"No JSON found in response: {response_text}")
        raise ValueError(f"No JSON found in response: {response_text[:100]}")

    try:
        return json.loads(json_text)
    except json.JSONDecodeError as e:
        logger.error(f"JSON parse error: {e}, text: {json_text[:200]}")
        raise ValueError(f"Invalid JSON from Claude: {json_text[:100]}")
