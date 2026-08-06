"""Read/write path for chat_messages — per-scan conversation history."""
from __future__ import annotations

from datetime import datetime, timezone

from db import get_connection
from models import ChatMessage


def save_message(scan_id: str, role: str, content: str) -> ChatMessage:
    """Append one message to the conversation and return it with its timestamp."""
    now = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO chat_messages (scan_id, role, content, created_at) VALUES (?, ?, ?, ?)",
            (scan_id, role, content, now),
        )
        conn.commit()
    finally:
        conn.close()
    return ChatMessage(role=role, content=content, created_at=now)


def load_messages(scan_id: str) -> list[ChatMessage]:
    """Return the full conversation history for a scan, oldest first."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT role, content, created_at FROM chat_messages WHERE scan_id = ? ORDER BY id",
            (scan_id,),
        ).fetchall()
        return [ChatMessage(role=r["role"], content=r["content"], created_at=r["created_at"]) for r in rows]
    finally:
        conn.close()
