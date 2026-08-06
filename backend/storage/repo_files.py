"""Read/write path for the `repo_files` table — R12's file-tree browser.

Kept separate from `storage/scans.py` (rather than folded into `get_scan`)
because the tree only ever needs path/size/language/finding_count, never the
rest of a `ScanReport` — a URL scan's report round-trips through `get_scan`
untouched either way, exactly the isolation R3 set this table up for.
"""
from __future__ import annotations

import sqlite3

from db import get_connection
from models import RepoFileEntry


def save_repo_files(conn: sqlite3.Connection, scan_id: str, files: list[RepoFileEntry]) -> None:
    """Insert one `repo_files` row per file. Takes an open connection so the
    caller (`repo_orchestrator._finalize`, via `storage.scans.save_scan`) can
    run this in the same transaction as the parent `scans` row."""
    for f in files:
        conn.execute(
            """
            INSERT INTO repo_files (scan_id, path, size, language, finding_count)
            VALUES (?, ?, ?, ?, ?)
            """,
            (scan_id, f.path, f.size, f.language, f.finding_count),
        )


def get_repo_files(scan_id: str) -> list[RepoFileEntry]:
    """Return every file in a repo scan's tree, path-sorted. Empty for a URL
    scan (or any scan_id with no matching rows) — not an error, the caller
    only needs to 404 when the *scan itself* doesn't exist."""
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT path, size, language, finding_count
            FROM repo_files
            WHERE scan_id = ?
            ORDER BY path
            """,
            (scan_id,),
        ).fetchall()
        return [
            RepoFileEntry(
                path=row["path"],
                size=row["size"],
                language=row["language"],
                finding_count=row["finding_count"],
            )
            for row in rows
        ]
    finally:
        conn.close()
