"""Tests that the migration list applies incrementally, not just from empty.

Every other test in this suite gets a database built by running all of
`MIGRATIONS` in one go, which proves a *fresh* schema works and nothing else.
The interesting case is the one a developer's machine actually hits: a database
already at the previous version, getting exactly the newest migration applied
on top of real rows.
"""
from __future__ import annotations

import sqlite3

import db
from db import MIGRATIONS, get_connection, init_db


def _build_at_version(path, version: int) -> None:
    """Create a database with migrations 1..`version` applied, the way
    `init_db` would have left it back when `version` was the newest."""
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)")
        for number, sql in MIGRATIONS:
            if number > version:
                break
            conn.executescript(sql)
        conn.execute("INSERT INTO schema_version (version) VALUES (?)", (version,))
        conn.commit()
    finally:
        conn.close()


def test_migration_13_applies_on_top_of_a_v12_database(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "v12.db")
    _build_at_version(db.DB_PATH, 12)

    # A row written before the migration existed -- the ALTER has to leave it
    # readable, with the new column simply empty.
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO scans (id, url, target_type, scanned_at, duration_ms, score, grade, created_at)
            VALUES ('s1', 'https://github.com/octo/demo', 'repo', '2026-01-01T00:00:00+00:00',
                    1, 80, 'B', '2026-01-01T00:00:00+00:00')
            """
        )
        conn.execute(
            """
            INSERT INTO fix_applications
                (id, scan_id, finding_key, fixer_slug, tier, state, plan_json, created_at, updated_at)
            VALUES ('a1', 's1', 'gitignore-present', 'gitignore-present', 1, 'merged', '',
                    '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00')
            """
        )
        conn.commit()
    finally:
        conn.close()

    init_db()

    conn = get_connection()
    try:
        version = conn.execute("SELECT version FROM schema_version").fetchone()["version"]
        row = conn.execute("SELECT * FROM fix_applications WHERE id = 'a1'").fetchone()
    finally:
        conn.close()

    assert version == MIGRATIONS[-1][0]
    assert row["verification_json"] is None
    assert row["state"] == "merged"


def test_init_db_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "twice.db")
    init_db()
    init_db()
    conn = get_connection()
    try:
        rows = conn.execute("SELECT version FROM schema_version").fetchall()
    finally:
        conn.close()
    assert [row["version"] for row in rows] == [MIGRATIONS[-1][0]]
