"""Read/write path for fix_suggestions — the AI fix cache.

Cache key is (finding_db_id, prompt_version). Bumping PROMPT_VERSION in
ai/prompts.py invalidates old cache rows without a migration.
"""
from __future__ import annotations

import json
import sqlite3

from db import get_connection
from models import FixSuggestion


def get_finding_db_id(
    conn: sqlite3.Connection, scan_id: str, finding_key: str
) -> int | None:
    """Look up the integer PK of a finding by scan + key slug."""
    row = conn.execute(
        "SELECT id FROM findings WHERE scan_id = ? AND finding_key = ?",
        (scan_id, finding_key),
    ).fetchone()
    return row["id"] if row else None


def get_cached_fix(
    conn: sqlite3.Connection, finding_id: int, prompt_version: str
) -> FixSuggestion | None:
    """Return a cached FixSuggestion, or None if no cache hit."""
    row = conn.execute(
        """
        SELECT content_json, model, created_at
        FROM fix_suggestions
        WHERE finding_id = ? AND prompt_version = ?
        """,
        (finding_id, prompt_version),
    ).fetchone()
    if row is None:
        return None
    try:
        data = json.loads(row["content_json"])
        data["model"] = row["model"]
        data["generated_at"] = row["created_at"]
        return FixSuggestion(**data)
    except Exception:
        return None


def load_fixes_for_scan(scan_id: str, prompt_version: str) -> dict[str, FixSuggestion]:
    """Return every cached fix for a scan, keyed by finding slug (not the
    integer DB id) — that's the key exporters and the frontend both use to
    match a fix back to its `Finding`. Empty dict if nothing is cached yet;
    export formats must render cleanly either way.
    """
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT f.finding_key, fx.content_json, fx.model, fx.created_at
            FROM fix_suggestions fx
            JOIN findings f ON f.id = fx.finding_id
            WHERE f.scan_id = ? AND fx.prompt_version = ?
            """,
            (scan_id, prompt_version),
        ).fetchall()
        result: dict[str, FixSuggestion] = {}
        for row in rows:
            try:
                data = json.loads(row["content_json"])
                data["model"] = row["model"]
                data["generated_at"] = row["created_at"]
                result[row["finding_key"]] = FixSuggestion(**data)
            except Exception:
                continue
        return result
    finally:
        conn.close()


def save_fix(
    conn: sqlite3.Connection,
    finding_id: int,
    prompt_version: str,
    model: str,
    suggestion: FixSuggestion,
) -> None:
    """Upsert a fix suggestion. Uses INSERT OR REPLACE so ?regenerate=true
    overwrites an existing row for the same (finding_id, prompt_version)."""
    payload = suggestion.model_dump(exclude={"model", "generated_at"})
    conn.execute(
        """
        INSERT OR REPLACE INTO fix_suggestions
            (finding_id, prompt_version, model, content_json, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (finding_id, prompt_version, model, json.dumps(payload), suggestion.generated_at),
    )
    conn.commit()
