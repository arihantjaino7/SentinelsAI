"""Tests for storage/remediation.py -- the fix_plans read/write path."""
from __future__ import annotations

from db import get_connection
from models import FilePatch, FixPlan
from storage.remediation import get_fix_plan, list_fix_plans, save_fix_plan


def _insert_bare_scan(scan_id: str) -> None:
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO scans (id, url, target_type, scanned_at, duration_ms, score, grade, created_at)
            VALUES (?, 'https://github.com/octo/demo', 'repo', '2026-01-01T00:00:00+00:00', 1, 80, 'B', '2026-01-01T00:00:00+00:00')
            """,
            (scan_id,),
        )
        conn.commit()
    finally:
        conn.close()


def _plan(finding_key: str = "gitignore-present") -> FixPlan:
    return FixPlan(
        finding_key=finding_key,
        fixer_slug="gitignore-present",
        tier=1,
        summary="Add a .gitignore",
        patches=[FilePatch(path=".gitignore", action="create", new_content=".env\n", diff="+.env")],
        created_at="2026-01-01T00:00:00+00:00",
    )


def test_get_fix_plan_returns_none_when_nothing_saved(temp_db):
    assert get_fix_plan("no-such-scan", "gitignore-present") is None


def test_save_and_get_round_trips(temp_db):
    _insert_bare_scan("scan1")
    save_fix_plan("scan1", _plan())
    loaded = get_fix_plan("scan1", "gitignore-present")
    assert loaded is not None
    assert loaded.finding_key == "gitignore-present"
    assert loaded.patches[0].path == ".gitignore"


def test_save_fix_plan_upserts_on_re_plan(temp_db):
    _insert_bare_scan("scan1")
    save_fix_plan("scan1", _plan())
    updated = _plan()
    updated.summary = "Updated summary"
    save_fix_plan("scan1", updated)

    loaded = get_fix_plan("scan1", "gitignore-present")
    assert loaded.summary == "Updated summary"
    assert len(list_fix_plans("scan1")) == 1  # replaced, not duplicated


def test_list_fix_plans_returns_every_plan_for_a_scan(temp_db):
    _insert_bare_scan("scan1")
    save_fix_plan("scan1", _plan("gitignore-present"))
    save_fix_plan("scan1", _plan("repo-readme-present"))
    plans = list_fix_plans("scan1")
    assert {p.finding_key for p in plans} == {"gitignore-present", "repo-readme-present"}


def test_list_fix_plans_scoped_to_one_scan(temp_db):
    _insert_bare_scan("scan1")
    _insert_bare_scan("scan2")
    save_fix_plan("scan1", _plan())
    assert list_fix_plans("scan2") == []
