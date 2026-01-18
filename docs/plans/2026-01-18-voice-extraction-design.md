# Voice Auto-Extraction Design

## Overview

Simplify the voice message flow by automatically extracting tasks, meetings, and notes from user messages without requiring manual intent selection.

## Core Flow

```
User sends message (voice or text)
         ↓
   [If voice: transcribe via OpenAI Whisper]
         ↓
   Claude Haiku processes the text:
   • Cleans filler words, off-topic content
   • Generates concise summary
   • Extracts tasks (with due dates if mentioned)
   • Extracts meetings (with agenda, participants, date)
         ↓
   Auto-save:
   • Note (always) — stores raw transcript + clean summary
   • Tasks (if found) — linked to source note
   • Meetings (if found) — linked to source note
         ↓
   Bot responds with summary + extracted items
   [Format based on IS_COMPACT_ANSWER]
   + "Open note" button for full transcription
```

## Key Decisions

| Decision | Choice |
|----------|--------|
| Save behavior | Auto-save immediately, no confirmation |
| Note creation | Always create Note with summary + transcript |
| Linking | Tasks/Meetings reference source Note via `source_note_id` |
| AI model | Claude Haiku (fast, cheap) |
| Response format | Configurable via `IS_COMPACT_ANSWER` env var |
| Full text access | "Open note" button |
| Existing commands | Keep /task, /meet, /note for explicit creation |

## Data Model Changes

### Task model — add field:
```python
source_note_id: Mapped[Optional[int]] = mapped_column(
    ForeignKey("notes.id"), nullable=True
)
```

### Meeting model — add field:
```python
source_note_id: Mapped[Optional[int]] = mapped_column(
    ForeignKey("notes.id"), nullable=True
)
```

### Note model — add relationships:
```python
extracted_tasks: Mapped[list["Task"]] = relationship(...)
extracted_meetings: Mapped[list["Meeting"]] = relationship(...)
```

### Config — add setting:
```python
is_compact_answer: bool = True  # from IS_COMPACT_ANSWER env var
```

## Response Formats

### Compact (`IS_COMPACT_ANSWER=true`):
```
📝 Call John about budget; schedule team sync for Q2

✅ Call John about budget (tomorrow)
📅 Team sync - Q2 planning (Friday)

[Open note]
```

### Detailed (`IS_COMPACT_ANSWER=false`):
```
📝 Summary saved

Tasks extracted:
• Call John about budget — due tomorrow

Meetings extracted:
• Team sync (Friday)
  Agenda: Discuss Q2 planning

[Open note]
```

### Edge Cases

| Scenario | Response |
|----------|----------|
| No tasks or meetings found | Just shows summary + "Open note" |
| Only tasks | Summary + tasks list, no meetings section |
| Only meeting | Summary + meeting, no tasks section |
| Voice transcription failed | Error message, no note saved |

## AI Extraction Service

### Function signature:
```python
async def extract_from_message(text: str) -> ExtractionResult:
    """
    Returns:
    - summary: str (clean, concise version)
    - tasks: list[{title, priority, due_date}]
    - meetings: list[{title, participants, agenda, date}]
    """
```

### Extraction rules:
- Priority defaults to "medium" unless urgency words detected ("urgent", "ASAP", "critical")
- Due dates parsed from natural language ("tomorrow", "Friday", "next week")
- Meeting dates same approach
- If nothing actionable found → just summary + note saved

## Implementation Structure

### Files to modify:

| File | Changes |
|------|---------|
| `bot/models.py` | Add `source_note_id` to Task and Meeting |
| `bot/config.py` | Add `is_compact_answer: bool` setting |
| `bot/handlers/voice.py` | Replace "ask intent" flow with auto-extraction |
| `bot/keyboards.py` | Add "Open note" inline button |
| `bot/handlers/callbacks.py` | Handle `note:view:{id}` callback |
| `.env` | Add `IS_COMPACT_ANSWER=true` |

### New files:

| File | Purpose |
|------|---------|
| `bot/services/extraction.py` | Claude API call + structured extraction logic |
| `bot/services/formatter.py` | Format response (compact vs detailed) |

### Code flow:
```
voice.py: handle_voice() / handle_text()
    ↓
extraction.py: extract_from_message(text)
    ↓
database: save Note, Tasks, Meetings
    ↓
formatter.py: format_response(result, is_compact)
    ↓
Send message + "Open note" button
```

## Environment Variables

Add to `.env`:
```
IS_COMPACT_ANSWER=true
```
