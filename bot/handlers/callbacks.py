from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from bot.handlers import meeting, note, project, task, voice
from bot.keyboards import meeting_actions_keyboard

router = Router()


@router.callback_query(F.data.startswith("intent:"))
async def handle_intent(callback: CallbackQuery, state: FSMContext):
    """Handle intent selection from voice without command."""
    user_id = callback.from_user.id
    intent = callback.data.split(":")[1]

    success = await voice.process_pending_transcript(user_id, intent, callback.message, state)
    if success:
        await callback.answer()
        # Edit original message to remove buttons
        await callback.message.edit_reply_markup(reply_markup=None)
    else:
        await callback.answer("Transcript expired. Please send again.", show_alert=True)


@router.callback_query(F.data.startswith("tasks:"))
async def handle_tasks_callback(callback: CallbackQuery):
    """Handle tasks-related callbacks."""
    parts = callback.data.split(":")
    action = parts[1]

    if action == "save":
        batch_id = parts[2] if len(parts) > 2 else ""
        count = await task.save_tasks(batch_id)
        if count:
            await callback.answer("Saved!")
            await callback.message.edit_text(
                f"✅ {count} tasks saved!\n\n/tasks — view all tasks"
            )
        else:
            await callback.answer("Tasks not found or already saved.", show_alert=True)
    elif action == "cancel":
        batch_id = parts[2] if len(parts) > 2 else ""
        await task.cancel_tasks(batch_id)
        await callback.answer("Cancelled")
        await callback.message.edit_text("🗑 Cancelled")


@router.callback_query(F.data.startswith("task:"))
async def handle_task_callback(callback: CallbackQuery):
    """Handle single task callbacks."""
    parts = callback.data.split(":")
    action = parts[1]

    if action in ("done", "toggle"):
        task_id = int(parts[2]) if len(parts) > 2 else 0
        is_done = await task.toggle_task(task_id)
        status = "completed" if is_done else "marked pending"
        await callback.answer(f"Task {status}!")


@router.callback_query(F.data.startswith("meeting:"))
async def handle_meeting_callback(callback: CallbackQuery, bot: Bot):
    """Handle meeting-related callbacks."""
    parts = callback.data.split(":")
    action = parts[1]

    if action == "save":
        batch_id = parts[2] if len(parts) > 2 else ""
        meeting_id = await meeting.save_meeting(batch_id)
        if meeting_id:
            await callback.answer("Saved!")
            await callback.message.edit_reply_markup(
                reply_markup=meeting_actions_keyboard(meeting_id, has_voice=True)
            )
        else:
            await callback.answer("Meeting not found or already saved.", show_alert=True)
    elif action == "cancel":
        batch_id = parts[2] if len(parts) > 2 else ""
        await meeting.cancel_meeting(batch_id)
        await callback.answer("Cancelled")
        await callback.message.edit_text("🗑 Cancelled")
    elif action == "replay":
        meeting_id = int(parts[2]) if len(parts) > 2 else 0
        m = await meeting.get_meeting(meeting_id)
        if m and m.voice_file_id:
            await bot.send_voice(
                chat_id=callback.message.chat.id,
                voice=m.voice_file_id,
                caption="🎙 Original recording"
            )
            await callback.answer()
        else:
            await callback.answer("Audio not available", show_alert=True)
    elif action == "copy":
        meeting_id = int(parts[2]) if len(parts) > 2 else 0
        m = await meeting.get_meeting(meeting_id)
        if m:
            # Send agenda as plain text for easy copying
            await bot.send_message(
                chat_id=callback.message.chat.id,
                text=f"📋 {m.title}\n\n{m.agenda}"
            )
            await callback.answer("Copied!")
        else:
            await callback.answer("Meeting not found", show_alert=True)


@router.callback_query(F.data.startswith("note:"))
async def handle_note_callback(callback: CallbackQuery, bot: Bot):
    """Handle note-related callbacks."""
    parts = callback.data.split(":")
    action = parts[1]

    if action == "replay":
        note_id = int(parts[2]) if len(parts) > 2 else 0
        n = await note.get_note(note_id)
        if n and n.voice_file_id:
            await bot.send_voice(
                chat_id=callback.message.chat.id,
                voice=n.voice_file_id,
                caption="🎙 Original recording"
            )
            await callback.answer()
        else:
            await callback.answer("Audio not available", show_alert=True)
    elif action == "delete":
        note_id = int(parts[2]) if len(parts) > 2 else 0
        success = await note.delete_note(note_id)
        if success:
            await callback.answer("Deleted!")
            await callback.message.edit_text("🗑 Note deleted")
        else:
            await callback.answer("Note not found", show_alert=True)


@router.callback_query(F.data.startswith("project:"))
async def handle_project_callback(callback: CallbackQuery, state: FSMContext):
    """Handle project-related callbacks."""
    parts = callback.data.split(":")
    action = parts[1]

    if action == "new":
        await project.start_new_project(callback.message, state)
        await callback.answer()
