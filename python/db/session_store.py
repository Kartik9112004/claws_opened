"""
db/session_store.py — Chat session & message persistence via Supabase REST API.
Mirrors the TypeScript db/supabase.ts functions.
"""
from __future__ import annotations

from db.supabase_client import get_supabase


def load_chat_history(chat_id: str | int) -> list[dict]:
    """Load conversation messages for a given chat_id (oldest first)."""
    sb = get_supabase()
    if not sb:
        return []
    try:
        res = (
            sb.table("messages")
            .select("role, content")
            .eq("chat_id", str(chat_id))
            .order("created_at", desc=False)
            .execute()
        )
        return [{"role": r["role"], "content": r["content"]} for r in (res.data or [])]
    except Exception as exc:
        print(f"[session_store] load_chat_history error: {exc}")
        return []


def save_message(
    chat_id: str | int,
    role: str,
    content: str,
    chat_name: str | None = None,
) -> None:
    """Upsert chat session then insert a single message."""
    sb = get_supabase()
    if not sb:
        return
    try:
        sb.table("chats").upsert({"id": str(chat_id), "name": chat_name}).execute()
        sb.table("messages").insert(
            {"chat_id": str(chat_id), "role": role, "content": content, "chat_name": chat_name}
        ).execute()
    except Exception as exc:
        print(f"[session_store] save_message error: {exc}")


def create_chat(chat_id: str, name: str) -> None:
    """Create or update a named chat session."""
    sb = get_supabase()
    if not sb:
        return
    try:
        sb.table("chats").upsert({"id": chat_id, "name": name}).execute()
    except Exception as exc:
        print(f"[session_store] create_chat error: {exc}")


def list_chats() -> list[dict]:
    """Return all chats ordered newest first."""
    sb = get_supabase()
    if not sb:
        return []
    try:
        res = (
            sb.table("chats")
            .select("id, name")
            .order("created_at", desc=True)
            .execute()
        )
        return [{"id": r["id"], "name": r.get("name") or r["id"]} for r in (res.data or [])]
    except Exception as exc:
        print(f"[session_store] list_chats error: {exc}")
        return []
