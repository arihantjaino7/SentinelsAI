"""Chatbot — answers questions about a completed scan.

No RAG, no vector store. A finished scan is 3-6k tokens; we stuff the whole
thing into context. Conversation history is DB-backed so it survives refresh.
"""
from __future__ import annotations

from ai.client import call_groq, get_api_key
from ai.prompts import build_chat_messages
from models import ChatMessage, ScanReport, ChecklistItem
from storage.chat import load_messages, save_message


async def answer(
    scan_id: str,
    report: ScanReport,
    checklist: list[ChecklistItem],
    question: str,
) -> ChatMessage | None:
    """Answer one question, persist both turns, return the assistant message.

    Returns None when no GROQ_API_KEY is set.
    """
    if not get_api_key():
        return None

    # Load conversation history as plain dicts for prompt assembly.
    history = [{"role": m.role, "content": m.content} for m in load_messages(scan_id)]

    messages = build_chat_messages(report, checklist, history, question)

    # More tokens than analyst — answers can be a few paragraphs.
    raw = await call_groq(messages, max_tokens=1000, reasoning_effort="low")
    if not raw:
        return None

    # Persist both turns before returning.
    save_message(scan_id, "user", question)
    return save_message(scan_id, "assistant", raw)
