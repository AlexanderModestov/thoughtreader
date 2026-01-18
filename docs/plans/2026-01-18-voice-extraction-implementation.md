# Voice Auto-Extraction Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the manual intent selection flow with automatic extraction of tasks, meetings, and notes from voice/text messages.

**Architecture:** Messages go through a single extraction service that calls Claude Haiku to clean text, generate summary, and extract structured items (tasks/meetings). Everything auto-saves: Note always created, Tasks/Meetings linked back to source Note.

**Tech Stack:** Python 3.10+, aiogram 3.x, SQLAlchemy 2.x async, Anthropic Claude Haiku, pydantic-settings

---

## Task 1: Add Config Setting

**Files:**
- Modify: `bot/config.py:4-27`

**Step 1: Add is_compact_answer setting**

Add to Settings class after line 21:

```python
# Response format
is_compact_answer: bool = True
```

**Step 2: Verify config loads**

Run: `python -c "from bot.config import settings; print(settings.is_compact_answer)"`
Expected: `True`

**Step 3: Commit**

```bash
git add bot/config.py
git commit -m "feat: add is_compact_answer config setting"
```

---

## Task 2: Update Data Models

**Files:**
- Modify: `bot/models.py:43-64` (Task model)
- Modify: `bot/models.py:89-109` (Meeting model)
- Modify: `bot/models.py:66-87` (Note model)

**Step 1: Add source_note_id to Task model**

Add after line 48 (after `project_id`):

```python
source_note_id: Mapped[Optional[int]] = mapped_column(ForeignKey("notes.id"), nullable=True)
```

Add relationship after line 63:

```python
source_note: Mapped[Optional["Note"]] = relationship("Note", back_populates="extracted_tasks")
```

**Step 2: Add source_note_id to Meeting model**

Add after line 94 (after `user_id`):

```python
source_note_id: Mapped[Optional[int]] = mapped_column(ForeignKey("notes.id"), nullable=True)
```

Add relationship after line 108:

```python
source_note: Mapped[Optional["Note"]] = relationship("Note", back_populates="extracted_meetings")
```

**Step 3: Add relationships to Note model**

Add after line 86 (after `project` relationship):

```python
extracted_tasks: Mapped[list["Task"]] = relationship("Task", back_populates="source_note")
extracted_meetings: Mapped[list["Meeting"]] = relationship("Meeting", back_populates="source_note")
```

**Step 4: Verify models compile**

Run: `python -c "from bot.models import Task, Meeting, Note; print('OK')"`
Expected: `OK`

**Step 5: Commit**

```bash
git add bot/models.py
git commit -m "feat: add source_note_id to Task and Meeting models"
```

---

## Task 3: Create Extraction Service

**Files:**
- Create: `bot/services/extraction.py`

**Step 1: Create ExtractionResult dataclass and extraction service**

```python
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
```

**Step 2: Verify service imports**

Run: `python -c "from bot.services.extraction import extract_from_message, ExtractionResult; print('OK')"`
Expected: `OK`

**Step 3: Commit**

```bash
git add bot/services/extraction.py
git commit -m "feat: add extraction service with Claude Haiku"
```

---

## Task 4: Create Formatter Service

**Files:**
- Create: `bot/services/formatter.py`

**Step 1: Create formatter service**

```python
from bot.config import settings
from bot.services.extraction import ExtractionResult


def format_extraction_response(result: ExtractionResult, note_id: int) -> str:
    """Format extraction result based on IS_COMPACT_ANSWER setting."""
    if settings.is_compact_answer:
        return _format_compact(result)
    else:
        return _format_detailed(result)


def _format_compact(result: ExtractionResult) -> str:
    """Compact format: summary + items on single lines."""
    lines = [f"📝 {result.summary}"]

    if result.tasks:
        lines.append("")
        for task in result.tasks:
            due = f" ({task.due_date})" if task.due_date else ""
            lines.append(f"✅ {task.title}{due}")

    if result.meetings:
        lines.append("")
        for meeting in result.meetings:
            participants = f" with {', '.join(meeting.participants)}" if meeting.participants else ""
            lines.append(f"📅 {meeting.title}{participants}")

    return "\n".join(lines)


def _format_detailed(result: ExtractionResult) -> str:
    """Detailed format: sections with headers."""
    lines = ["📝 *Summary saved*", "", result.summary]

    if result.tasks:
        lines.append("")
        lines.append("*Tasks extracted:*")
        for task in result.tasks:
            due = f" — due {task.due_date}" if task.due_date else ""
            priority_emoji = {"urgent": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}
            emoji = priority_emoji.get(task.priority, "🟡")
            lines.append(f"• {emoji} {task.title}{due}")

    if result.meetings:
        lines.append("")
        lines.append("*Meetings extracted:*")
        for meeting in result.meetings:
            lines.append(f"• {meeting.title}")
            if meeting.participants:
                lines.append(f"  Participants: {', '.join(meeting.participants)}")
            if meeting.agenda:
                lines.append(f"  Agenda: {'; '.join(meeting.agenda)}")

    return "\n".join(lines)
```

**Step 2: Verify service imports**

Run: `python -c "from bot.services.formatter import format_extraction_response; print('OK')"`
Expected: `OK`

**Step 3: Commit**

```bash
git add bot/services/formatter.py
git commit -m "feat: add response formatter service"
```

---

## Task 5: Add Open Note Keyboard

**Files:**
- Modify: `bot/keyboards.py:1-55`

**Step 1: Add open_note_keyboard function**

Add after line 31 (after `note_actions_keyboard`):

```python
def open_note_keyboard(note_id: int) -> InlineKeyboardMarkup:
    """Button to open full note."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📄 Open note", callback_data=f"note:view:{note_id}")]
    ])
```

**Step 2: Verify keyboard imports**

Run: `python -c "from bot.keyboards import open_note_keyboard; print('OK')"`
Expected: `OK`

**Step 3: Commit**

```bash
git add bot/keyboards.py
git commit -m "feat: add open note keyboard button"
```

---

## Task 6: Add Note View Callback

**Files:**
- Modify: `bot/handlers/callbacks.py:109-135`

**Step 1: Add view action to handle_note_callback**

Add after line 114 (inside `handle_note_callback`, before `if action == "replay"`):

```python
    if action == "view":
        note_id = int(parts[2]) if len(parts) > 2 else 0
        n = await note.get_note(note_id)
        if n:
            text = n.raw_transcript or n.content
            await callback.message.answer(
                f"📄 *Full transcription:*\n\n{text}",
                reply_markup=note_actions_keyboard(n.id, has_voice=bool(n.voice_file_id))
            )
            await callback.answer()
        else:
            await callback.answer("Note not found", show_alert=True)
        return
```

**Step 2: Import note_actions_keyboard**

At the top of callbacks.py, ensure `note_actions_keyboard` is imported:

```python
from bot.keyboards import meeting_actions_keyboard, note_actions_keyboard
```

**Step 3: Commit**

```bash
git add bot/handlers/callbacks.py
git commit -m "feat: add note view callback handler"
```

---

## Task 7: Update Voice Handler - Auto Extraction

**Files:**
- Modify: `bot/handlers/voice.py:1-110`

**Step 1: Replace voice.py with new auto-extraction flow**

```python
from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy import select

from bot.database import get_session
from bot.handlers.meeting import MeetingStates
from bot.handlers.note import NoteStates
from bot.handlers.task import TaskStates
from bot.handlers import meeting, note, task
from bot.keyboards import open_note_keyboard
from bot.models import Meeting, Note, Project, Task, User
from bot.services.extraction import extract_from_message
from bot.services.formatter import format_extraction_response
from bot.services.transcription import transcribe

router = Router()


def detect_project(text: str, projects: list[Project]) -> Project | None:
    """Simple keyword matching for project detection."""
    text_lower = text.lower()
    for project in projects:
        if not project.keywords:
            continue
        keywords = [k.strip() for k in project.keywords.split(",")]
        for keyword in keywords:
            if keyword and keyword.lower() in text_lower:
                return project
    return None


async def process_auto_extraction(message: Message, text: str, user_id: int, voice_file_id: str = None, voice_duration: int = None):
    """Process message with auto-extraction: extract tasks, meetings, save note."""
    # Extract using Claude
    try:
        result = await extract_from_message(text)
    except Exception as e:
        await message.answer(f"Error processing: {str(e)}")
        return

    async with get_session() as db:
        # Get user
        user_result = await db.execute(
            select(User).where(User.telegram_id == user_id)
        )
        user = user_result.scalar()

        if not user:
            await message.answer("Please start the bot with /start first.")
            return

        # Get projects
        projects_result = await db.execute(
            select(Project).where(Project.user_id == user.id)
        )
        projects = list(projects_result.scalars().all())
        default_project = next((p for p in projects if p.is_default), None)

        # Create note (always)
        note_obj = Note(
            user_id=user.id,
            project_id=default_project.id if default_project else None,
            title=result.summary[:100] if result.summary else None,
            content=result.summary,
            raw_transcript=text,
            voice_file_id=voice_file_id,
            voice_duration=voice_duration
        )
        db.add(note_obj)
        await db.flush()  # Get note ID

        # Create tasks (if any)
        for extracted_task in result.tasks:
            project = detect_project(extracted_task.title, projects) or default_project
            task_obj = Task(
                user_id=user.id,
                project_id=project.id if project else None,
                source_note_id=note_obj.id,
                title=extracted_task.title,
                priority=extracted_task.priority,
                due_date=extracted_task.due_date,
                raw_text=text,
                voice_file_id=voice_file_id
            )
            db.add(task_obj)

        # Create meetings (if any)
        for extracted_meeting in result.meetings:
            meeting_obj = Meeting(
                user_id=user.id,
                source_note_id=note_obj.id,
                title=extracted_meeting.title,
                participants=", ".join(extracted_meeting.participants),
                agenda="\n".join(f"- {item}" for item in extracted_meeting.agenda),
                goal=extracted_meeting.goal,
                raw_transcript=text,
                voice_file_id=voice_file_id,
                voice_duration=voice_duration
            )
            db.add(meeting_obj)

        await db.commit()

        # Format and send response
        response = format_extraction_response(result, note_obj.id)
        await message.answer(
            response,
            reply_markup=open_note_keyboard(note_obj.id)
        )


@router.message(F.voice)
async def handle_voice(message: Message, state: FSMContext, bot: Bot):
    """Handle voice message - check state or auto-extract."""
    user_id = message.from_user.id
    voice = message.voice

    # Download and transcribe
    file = await bot.get_file(voice.file_id)
    audio_bytes = await bot.download_file(file.file_path)

    processing_msg = await message.answer("🎙 Processing...")

    try:
        text = await transcribe(audio_bytes.read())
    except Exception as e:
        await processing_msg.edit_text(f"Error transcribing: {str(e)}")
        return

    await processing_msg.delete()

    # Check if awaiting specific type (from /task, /meet, /note commands)
    current_state = await state.get_state()

    if current_state == TaskStates.waiting_for_task_input:
        await task.process_tasks(message, text, user_id, state, voice.file_id)
    elif current_state == MeetingStates.waiting_for_meeting_input:
        await meeting.process_meeting(message, text, user_id, state, voice.file_id, voice.duration)
    elif current_state == NoteStates.waiting_for_note_input:
        await note.process_note(message, text, user_id, state, voice.file_id, voice.duration)
    else:
        # Auto-extraction flow
        await process_auto_extraction(message, text, user_id, voice.file_id, voice.duration)


@router.message(F.text)
async def handle_text(message: Message, state: FSMContext):
    """Handle text message - check state or auto-extract."""
    user_id = message.from_user.id
    text = message.text

    # Skip commands
    if text.startswith("/"):
        return

    # Check if awaiting specific type
    current_state = await state.get_state()

    if current_state == TaskStates.waiting_for_task_input:
        await task.process_tasks(message, text, user_id, state)
    elif current_state == MeetingStates.waiting_for_meeting_input:
        await meeting.process_meeting(message, text, user_id, state)
    elif current_state == NoteStates.waiting_for_note_input:
        await note.process_note(message, text, user_id, state)
    else:
        # Auto-extraction flow
        await process_auto_extraction(message, text, user_id)
```

**Step 2: Verify voice handler imports**

Run: `python -c "from bot.handlers.voice import router; print('OK')"`
Expected: `OK`

**Step 3: Commit**

```bash
git add bot/handlers/voice.py
git commit -m "feat: replace intent selection with auto-extraction flow"
```

---

## Task 8: Clean Up Old Intent Code

**Files:**
- Modify: `bot/handlers/callbacks.py:11-24`
- Modify: `bot/keyboards.py:4-12`

**Step 1: Remove handle_intent callback (optional, can keep for backward compatibility)**

The intent callback handler at lines 11-24 in callbacks.py can be removed since we no longer use it. However, keeping it won't break anything.

**Step 2: Remove intent_keyboard (optional)**

The `intent_keyboard` function at lines 4-12 in keyboards.py can be removed since we no longer use it. However, keeping it won't break anything.

**Step 3: Commit (if changes made)**

```bash
git add bot/handlers/callbacks.py bot/keyboards.py
git commit -m "chore: remove unused intent selection code"
```

---

## Task 9: Update .env.example

**Files:**
- Create or modify: `.env.example`

**Step 1: Add IS_COMPACT_ANSWER to env example**

Add to .env.example (create if doesn't exist):

```
# Telegram
TELEGRAM_BOT_TOKEN=your_bot_token

# Anthropic
ANTHROPIC_API_KEY=your_anthropic_key

# OpenAI (for Whisper)
OPENAI_API_KEY=your_openai_key

# Response format (true = compact, false = detailed)
IS_COMPACT_ANSWER=true
```

**Step 2: Commit**

```bash
git add .env.example
git commit -m "docs: add IS_COMPACT_ANSWER to env example"
```

---

## Task 10: Manual Testing

**Step 1: Start the bot**

Run: `python -m bot.main`

**Step 2: Test auto-extraction with text**

Send text message: "Need to call John tomorrow about the budget and schedule a team meeting for Friday to discuss Q2 plans with Alice and Bob"

Expected response (compact):
```
📝 Call John about budget; schedule team meeting for Q2 planning

✅ Call John about budget (2026-01-19)
📅 Team meeting with Alice, Bob
```

**Step 3: Test "Open note" button**

Click "Open note" button.
Expected: Full transcription displayed.

**Step 4: Test explicit commands still work**

Send `/task` then "Buy groceries"
Expected: Old flow with Save/Cancel buttons.

**Step 5: Final commit**

```bash
git add -A
git commit -m "feat: voice auto-extraction complete"
```

---

## Summary

| Task | Files | Description |
|------|-------|-------------|
| 1 | config.py | Add is_compact_answer setting |
| 2 | models.py | Add source_note_id to Task/Meeting |
| 3 | services/extraction.py | Create extraction service |
| 4 | services/formatter.py | Create formatter service |
| 5 | keyboards.py | Add open_note_keyboard |
| 6 | handlers/callbacks.py | Add note:view callback |
| 7 | handlers/voice.py | Replace with auto-extraction |
| 8 | callbacks.py, keyboards.py | Clean up old intent code |
| 9 | .env.example | Document new env var |
| 10 | - | Manual testing |
