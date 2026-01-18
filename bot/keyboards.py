from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def intent_keyboard() -> InlineKeyboardMarkup:
    """Choice of type for voice without command."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📋 Meeting", callback_data="intent:meeting"),
            InlineKeyboardButton(text="✅ Tasks", callback_data="intent:tasks"),
            InlineKeyboardButton(text="📝 Note", callback_data="intent:note"),
        ]
    ])


def confirm_keyboard(prefix: str, batch_id: str) -> InlineKeyboardMarkup:
    """Confirmation of saving."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Save", callback_data=f"{prefix}:save:{batch_id}"),
            InlineKeyboardButton(text="🗑 Cancel", callback_data=f"{prefix}:cancel:{batch_id}"),
        ]
    ])


def note_actions_keyboard(note_id: int, has_voice: bool) -> InlineKeyboardMarkup:
    """Actions with note."""
    buttons = []
    if has_voice:
        buttons.append(InlineKeyboardButton(text="🎙 Replay", callback_data=f"note:replay:{note_id}"))
    buttons.append(InlineKeyboardButton(text="🗑 Delete", callback_data=f"note:delete:{note_id}"))
    return InlineKeyboardMarkup(inline_keyboard=[buttons])


def meeting_actions_keyboard(meeting_id: int, has_voice: bool) -> InlineKeyboardMarkup:
    """Actions with meeting."""
    buttons = []
    if has_voice:
        buttons.append(InlineKeyboardButton(text="🎙 Replay", callback_data=f"meeting:replay:{meeting_id}"))
    buttons.append(InlineKeyboardButton(text="📋 Copy", callback_data=f"meeting:copy:{meeting_id}"))
    return InlineKeyboardMarkup(inline_keyboard=[buttons])


def task_done_keyboard(task_id: int) -> InlineKeyboardMarkup:
    """Mark task as done."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Done", callback_data=f"task:done:{task_id}")]
    ])


def projects_keyboard() -> InlineKeyboardMarkup:
    """Projects list actions."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ New project", callback_data="project:new")]
    ])
