import json
import logging
import re
from dataclasses import dataclass, field
from datetime import date

from anthropic import AsyncAnthropic

from bot.config import settings

logger = logging.getLogger(__name__)

_client: AsyncAnthropic | None = None


def _get_client() -> AsyncAnthropic:
    global _client
    if _client is None:
        _client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    return _client


@dataclass
class ExtractedTask:
    title: str
    priority: str = "medium"
    due_date: str | None = None


@dataclass
class ExtractedMeeting:
    title: str
    participants: list[str] = field(default_factory=list)
    agenda: list[str] = field(default_factory=list)
    goal: str | None = None


@dataclass
class ExtractionResult:
    summary: str
    cleaned_text: str
    tasks: list[ExtractedTask] = field(default_factory=list)
    meetings: list[ExtractedMeeting] = field(default_factory=list)


EXTRACTION_PROMPT = """You are an assistant that processes voice transcriptions. Analyze the text and:

1. CLEAN: Remove filler words (um, uh, like, you know), false starts, and off-topic content
2. SUMMARIZE: Create a 1-2 sentence summary of the core content
3. EXTRACT TASKS: Find action items with deadlines/priorities
4. EXTRACT MEETINGS: Find scheduled events with participants/agendas

Text: {text}
Today: {today}

Reply ONLY with valid JSON:
{{
  "summary": "concise 1-2 sentence summary",
  "cleaned_text": "cleaned version without filler words",
  "tasks": [
    {{"title": "task description", "priority": "low/medium/high/urgent", "due_date": "YYYY-MM-DD or null"}}
  ],
  "meetings": [
    {{"title": "meeting title", "participants": ["name1"], "agenda": ["item1"], "goal": "goal or null"}}
  ]
}}

Priority rules:
- "urgent", "asap", "critical" -> urgent
- "important", "priority" -> high
- Default -> medium
- "someday", "not urgent" -> low

Date rules:
- "tomorrow" -> tomorrow's date
- "Monday" -> next Monday
- "next week" -> Monday of next week
- Not specified -> null

If no tasks found, return empty array. If no meetings found, return empty array.
Return ONLY the JSON, no markdown."""


def _extract_json(text: str) -> str:
    text = text.strip()
    json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', text)
    if json_match:
        return json_match.group(1).strip()
    return text


async def extract_from_message(text: str) -> ExtractionResult:
    """Extract summary, tasks, and meetings from text using Claude Haiku."""
    client = _get_client()

    prompt = EXTRACTION_PROMPT.format(
        text=text,
        today=date.today().isoformat()
    )

    logger.info(f"Extracting from text, length: {len(text)}")

    response = await client.messages.create(
        model="claude-3-haiku-20240307",
        max_tokens=settings.max_tokens,
        messages=[{"role": "user", "content": prompt}]
    )

    if not response.content:
        logger.error("Empty response from Claude")
        raise ValueError("Empty response from Claude")

    response_text = response.content[0].text
    logger.info(f"Claude response: {response_text[:200]}...")

    json_text = _extract_json(response_text)

    try:
        data = json.loads(json_text)
    except json.JSONDecodeError as e:
        logger.error(f"JSON parse error: {e}")
        raise ValueError(f"Invalid JSON: {json_text[:100]}")

    tasks = [
        ExtractedTask(
            title=t["title"],
            priority=t.get("priority", "medium"),
            due_date=t.get("due_date")
        )
        for t in data.get("tasks", [])
    ]

    meetings = [
        ExtractedMeeting(
            title=m["title"],
            participants=m.get("participants", []),
            agenda=m.get("agenda", []),
            goal=m.get("goal")
        )
        for m in data.get("meetings", [])
    ]

    return ExtractionResult(
        summary=data.get("summary", ""),
        cleaned_text=data.get("cleaned_text", text),
        tasks=tasks,
        meetings=meetings
    )
