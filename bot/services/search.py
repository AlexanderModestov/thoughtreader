from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.models import Meeting, Note, Task


@dataclass
class SearchResult:
    entity_type: str  # "task", "note", "meeting"
    entity_id: int
    title: str
    created_at: datetime
    is_done: bool = False  # only for tasks


async def search(user_id: int, query: str, db: AsyncSession) -> list[SearchResult]:
    """Search across tasks, notes, and meetings."""
    results = []
    pattern = f"%{query}%"

    # Tasks
    tasks_result = await db.execute(
        select(Task)
        .where(Task.user_id == user_id)
        .where(Task.title.ilike(pattern))
        .limit(10)
    )
    for task in tasks_result.scalars():
        results.append(SearchResult(
            entity_type="task",
            entity_id=task.id,
            title=task.title,
            created_at=task.created_at,
            is_done=task.is_done
        ))

    # Notes
    notes_result = await db.execute(
        select(Note)
        .where(Note.user_id == user_id)
        .where(Note.content.ilike(pattern) | Note.title.ilike(pattern))
        .limit(10)
    )
    for note in notes_result.scalars():
        results.append(SearchResult(
            entity_type="note",
            entity_id=note.id,
            title=note.title or note.content[:50],
            created_at=note.created_at
        ))

    # Meetings
    meetings_result = await db.execute(
        select(Meeting)
        .where(Meeting.user_id == user_id)
        .where(Meeting.title.ilike(pattern) | Meeting.agenda.ilike(pattern))
        .limit(10)
    )
    for meeting in meetings_result.scalars():
        results.append(SearchResult(
            entity_type="meeting",
            entity_id=meeting.id,
            title=meeting.title,
            created_at=meeting.created_at
        ))

    # Sort by date descending
    results.sort(key=lambda x: x.created_at, reverse=True)
    return results[:10]
