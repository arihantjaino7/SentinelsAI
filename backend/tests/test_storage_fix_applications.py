"""Tests for the `fix_applications` and `audit_log` half of
storage/remediation.py, plus the migration-12 guarantees the audit trail
depends on (PLAN-v5.md conflict #9).
"""
from __future__ import annotations

import sqlite3

import pytest

from db import get_connection
from models import FilePatch, FixApplicationState, FixPlan
from storage.remediation import (
    active_fix_applications,
    count_prs_for_scan,
    count_prs_since,
    list_audit,
    list_fix_applications,
    save_fix_application,
    save_fix_plan,
    update_fix_application_state,
    write_audit,
)


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


def test_application_round_trips_with_its_plan_snapshot(temp_db):
    _insert_bare_scan("scan1")
    application = save_fix_application(
        "scan1", _plan(), FixApplicationState.PR_OPEN,
        branch="sentinels/fix-scan1-1", pr_url="https://x/pull/1", pr_number=1,
    )
    assert application.plan is not None
    assert application.plan.patches[0].path == ".gitignore"
    assert application.pr_number == 1


def test_the_snapshot_survives_the_plan_being_replaced(temp_db):
    """The whole reason `plan_json` exists. `fix_plans` is INSERT OR REPLACE'd
    on every re-plan, so an audit row that merely *pointed* at one would end
    up describing a different patch than the one in the pull request."""
    _insert_bare_scan("scan1")
    save_fix_plan("scan1", _plan())
    save_fix_application("scan1", _plan(), FixApplicationState.PR_OPEN, branch="b", pr_number=1)

    replanned = _plan()
    replanned.summary = "A completely different fix"
    replanned.patches = [
        FilePatch(path="README.md", action="create", new_content="hi", diff="+hi")
    ]
    save_fix_plan("scan1", replanned)

    application = list_fix_applications("scan1")[0]
    assert application.plan.summary == "Add a .gitignore"
    assert application.plan.patches[0].path == ".gitignore"


def test_deleting_the_plan_row_does_not_delete_the_audit_row(temp_db):
    """Migration 12 changed this FK from ON DELETE CASCADE to SET NULL."""
    _insert_bare_scan("scan1")
    save_fix_plan("scan1", _plan())
    save_fix_application("scan1", _plan(), FixApplicationState.PR_OPEN, branch="b", pr_number=1)

    conn = get_connection()
    try:
        conn.execute("DELETE FROM fix_plans WHERE scan_id = 'scan1'")
        conn.commit()
        row = conn.execute("SELECT fix_plan_id FROM fix_applications").fetchone()
    finally:
        conn.close()

    assert row["fix_plan_id"] is None
    assert len(list_fix_applications("scan1")) == 1


def test_the_partial_index_rejects_a_second_active_row(temp_db):
    _insert_bare_scan("scan1")
    save_fix_application("scan1", _plan(), FixApplicationState.PR_OPEN, branch="b", pr_number=1)
    with pytest.raises(sqlite3.IntegrityError):
        save_fix_application("scan1", _plan(), FixApplicationState.PR_OPEN, branch="b2", pr_number=2)


def test_the_partial_index_allows_a_retry_after_a_failure(temp_db):
    """A failed attempt must not permanently block the finding. That is what
    makes the index *partial* rather than a plain UNIQUE constraint."""
    _insert_bare_scan("scan1")
    save_fix_application("scan1", _plan(), FixApplicationState.FAILED, branch="b", pr_number=1)
    save_fix_application("scan1", _plan(), FixApplicationState.PR_OPEN, branch="b2", pr_number=2)
    assert len(list_fix_applications("scan1")) == 2


def test_active_fix_applications_ignores_terminal_rows(temp_db):
    _insert_bare_scan("scan1")
    save_fix_application("scan1", _plan("a"), FixApplicationState.ABANDONED, branch="b")
    save_fix_application("scan1", _plan("b"), FixApplicationState.PR_OPEN, branch="b2", pr_number=2)
    active = active_fix_applications("scan1", ["a", "b"])
    assert set(active) == {"b"}


def test_state_transitions_are_persisted(temp_db):
    _insert_bare_scan("scan1")
    application = save_fix_application(
        "scan1", _plan(), FixApplicationState.PR_OPEN, branch="b", pr_number=1
    )
    update_fix_application_state(application.id, FixApplicationState.MERGED)
    assert list_fix_applications("scan1")[0].state == FixApplicationState.MERGED


def test_pr_counts_are_per_branch_not_per_row(temp_db):
    """One apply writes a row per finding but opens exactly one pull request,
    so the budget counts branches."""
    _insert_bare_scan("scan1")
    save_fix_application("scan1", _plan("a"), FixApplicationState.PR_OPEN, branch="b1", pr_number=1)
    save_fix_application("scan1", _plan("b"), FixApplicationState.PR_OPEN, branch="b1", pr_number=1)
    assert count_prs_for_scan("scan1") == 1
    assert count_prs_since(hours=1) == 1


def test_failed_attempts_do_not_consume_budget(temp_db):
    _insert_bare_scan("scan1")
    save_fix_application("scan1", _plan("a"), FixApplicationState.FAILED, branch="b1")
    assert count_prs_for_scan("scan1") == 0


def test_audit_rows_are_written_and_read_back_in_order(temp_db):
    _insert_bare_scan("scan1")
    write_audit(None, "scan1", "gitignore-present", "pr_opened", "branch=b pr=#1")
    write_audit(None, "scan1", "gitignore-present", "pr_merged", "")
    rows = list_audit("scan1")
    assert [row["action"] for row in rows] == ["pr_opened", "pr_merged"]
    assert rows[0]["detail"] == "branch=b pr=#1"
