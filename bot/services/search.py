from bot.database import supabase


def search(user_id: int, query: str) -> list[dict]:
    """Search across tasks, notes, and meetings."""
    results = []
    pattern = f"%{query}%"

    # Tasks
    tasks_result = supabase.table("tr_tasks").select("*").eq("user_id", user_id).ilike("title", pattern).limit(10).execute()
    for task in tasks_result.data:
        results.append({
            "entity_type": "task",
            "entity_id": task["id"],
            "title": task["title"],
            "created_at": task["created_at"],
            "is_done": task["is_done"]
        })

    # Notes - search in title and content
    notes_result = supabase.table("tr_notes").select("*").eq("user_id", user_id).or_(f"title.ilike.{pattern},content.ilike.{pattern}").limit(10).execute()
    for note in notes_result.data:
        results.append({
            "entity_type": "note",
            "entity_id": note["id"],
            "title": note.get("title") or note["content"][:50],
            "created_at": note["created_at"],
            "is_done": False
        })

    # Meetings - search in title and agenda
    meetings_result = supabase.table("tr_meetings").select("*").eq("user_id", user_id).or_(f"title.ilike.{pattern},agenda.ilike.{pattern}").limit(10).execute()
    for meeting in meetings_result.data:
        results.append({
            "entity_type": "meeting",
            "entity_id": meeting["id"],
            "title": meeting["title"],
            "created_at": meeting["created_at"],
            "is_done": False
        })

    # Sort by date descending
    results.sort(key=lambda x: x["created_at"], reverse=True)
    return results[:10]
