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
