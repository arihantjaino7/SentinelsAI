"""Read/write path for `scan_repo_links` (PLAN-v5 Stage D) -- the table that
lets a URL scan borrow a repository's write path the same way a repo scan
already has one for free through its own GitHub URL.

One link per scan (`scan_id` is the primary key): a URL scan targets one
site, so at most one repository is ever "the thing that serves it." Linking
again replaces the row rather than adding a second one, mirroring
`storage/installations.py`'s `save_installation` precedent for an
`ON CONFLICT ... DO UPDATE`.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from db import get_connection
from models import ScanRepoLink


def _row_to_link(row: sqlite3.Row) -> ScanRepoLink:
    return ScanRepoLink(
        scan_id=row["scan_id"],
        user_id=row["user_id"],
        installation_id=row["installation_id"],
        owner=row["owner"],
        repo=row["repo"],
        ref=row["ref"],
        linked_at=row["linked_at"],
    )


def save_scan_repo_link(
    scan_id: str,
    user_id: int,
    installation_id: int,
    owner: str,
    repo: str,
    ref: str | None = None,
) -> ScanRepoLink:
    """Link (or re-link) a URL scan to a repository. Re-linking replaces the
    row wholesale -- a scan is never linked to two repositories at once."""
    now = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO scan_repo_links
                (scan_id, user_id, installation_id, owner, repo, ref, linked_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(scan_id) DO UPDATE SET
                user_id         = excluded.user_id,
                installation_id = excluded.installation_id,
                owner           = excluded.owner,
                repo            = excluded.repo,
                ref             = excluded.ref,
                linked_at       = excluded.linked_at
            """,
            (scan_id, user_id, installation_id, owner, repo, ref, now),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM scan_repo_links WHERE scan_id = ?", (scan_id,)
        ).fetchone()
        return _row_to_link(row)
    finally:
        conn.close()


def get_scan_repo_link(scan_id: str) -> ScanRepoLink | None:
    """The repository linked to this scan, or `None` if it isn't linked --
    the normal state for every scan taken before this stage, and for any
    URL scan whose fix flow nobody has started yet."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM scan_repo_links WHERE scan_id = ?", (scan_id,)
        ).fetchone()
        return _row_to_link(row) if row is not None else None
    finally:
        conn.close()


def delete_scan_repo_link(scan_id: str, user_id: int) -> bool:
    """Unlink, scoped to the caller -- the same "wrong owner behaves like no
    row at all" shape `storage/installations.py`'s `revoke_installation` uses."""
    conn = get_connection()
    try:
        cursor = conn.execute(
            "DELETE FROM scan_repo_links WHERE scan_id = ? AND user_id = ?",
            (scan_id, user_id),
        )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()
