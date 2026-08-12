"""Read/write path for the three remediation tables: `fix_plans` (Stage A),
and `fix_applications` + `audit_log` (Stage B, where a plan actually becomes
a pull request).

The one thing to know about `fix_applications`: it stores its own frozen
`plan_json` rather than trusting `fix_plan_id` to still describe what was
applied. `fix_plans` is replaced wholesale on every re-plan, so the row a
foreign key points at can become a *different* patch — or disappear. An audit
record whose meaning changes underneath it is not an audit record
(PLAN-v5.md conflict #9).
"""
from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timedelta, timezone

from db import get_connection
from models import FixApplication, FixApplicationState, FixPlan

# States that mean "this attempt is over" -- and therefore no longer occupy
# the one active slot a (scan, finding) pair is allowed. Kept here next to the
# queries that use it, matching the partial unique index in db.py's _V12_SCHEMA.
TERMINAL_STATES = ("failed", "abandoned")


def save_fix_plan(scan_id: str, plan: FixPlan) -> None:
    """Upsert one finding's plan. `INSERT OR REPLACE` on the
    `(scan_id, finding_key)` UNIQUE constraint -- re-planning always
    reflects the current repo state, never accumulates stale rows."""
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT OR REPLACE INTO fix_plans
                (scan_id, finding_key, fixer_slug, tier, summary, plan_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                scan_id,
                plan.finding_key,
                plan.fixer_slug,
                plan.tier,
                plan.summary,
                plan.model_dump_json(),
                plan.created_at,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def get_fix_plan(scan_id: str, finding_key: str) -> FixPlan | None:
    """The most recently persisted plan for one finding, or `None` if it's
    never been planned (or planned and rejected -- rejected plans are never
    saved)."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT plan_json FROM fix_plans WHERE scan_id = ? AND finding_key = ?",
            (scan_id, finding_key),
        ).fetchone()
        if row is None:
            return None
        return FixPlan.model_validate_json(row["plan_json"])
    finally:
        conn.close()


def list_fix_plans(scan_id: str) -> list[FixPlan]:
    """Every persisted plan for a scan, in the order they were first
    created."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT plan_json FROM fix_plans WHERE scan_id = ? ORDER BY id",
            (scan_id,),
        ).fetchall()
        return [FixPlan.model_validate_json(row["plan_json"]) for row in rows]
    finally:
        conn.close()


def fix_plan_row_id(scan_id: str, finding_key: str) -> int | None:
    """The `fix_plans.id` for one finding, for `fix_applications.fix_plan_id`
    to point at while it lasts. `None` if the plan was never persisted (a live
    preview, for instance) -- which is fine, the column is nullable precisely
    so an application does not depend on a plan row existing."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT id FROM fix_plans WHERE scan_id = ? AND finding_key = ?",
            (scan_id, finding_key),
        ).fetchone()
        return row["id"] if row is not None else None
    finally:
        conn.close()


def _row_to_application(row: sqlite3.Row) -> FixApplication:
    plan_json = row["plan_json"]
    return FixApplication(
        id=row["id"],
        scan_id=row["scan_id"],
        finding_key=row["finding_key"],
        fixer_slug=row["fixer_slug"],
        tier=row["tier"],
        state=FixApplicationState(row["state"]),
        pr_url=row["pr_url"],
        pr_number=row["pr_number"],
        branch=row["branch"],
        plan=FixPlan.model_validate_json(plan_json) if plan_json else None,
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def save_fix_application(
    scan_id: str,
    plan: FixPlan,
    state: FixApplicationState,
    branch: str | None = None,
    pr_url: str | None = None,
    pr_number: int | None = None,
) -> FixApplication:
    """Write one audit row for one finding, snapshotting the plan as applied.

    `plan_json` is serialized here, from the object that was actually pushed,
    rather than re-read from `fix_plans` later. That is the whole invariant:
    the snapshot is taken at the moment of truth, not reconstructed
    afterwards from a table that may have moved on.
    """
    now = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    try:
        application_id = str(uuid.uuid4())
        conn.execute(
            """
            INSERT INTO fix_applications
                (id, scan_id, fix_plan_id, finding_key, fixer_slug, tier, state,
                 pr_url, pr_number, branch, plan_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                application_id,
                scan_id,
                fix_plan_row_id(scan_id, plan.finding_key),
                plan.finding_key,
                plan.fixer_slug,
                plan.tier,
                state.value,
                pr_url,
                pr_number,
                branch,
                plan.model_dump_json(),
                now,
                now,
            ),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM fix_applications WHERE id = ?", (application_id,)
        ).fetchone()
        return _row_to_application(row)
    finally:
        conn.close()


def list_fix_applications(scan_id: str) -> list[FixApplication]:
    """Every application recorded for a scan, oldest first."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM fix_applications WHERE scan_id = ? ORDER BY created_at, id",
            (scan_id,),
        ).fetchall()
        return [_row_to_application(row) for row in rows]
    finally:
        conn.close()


def active_fix_applications(scan_id: str, finding_keys: list[str]) -> dict[str, FixApplication]:
    """The non-terminal application for each of `finding_keys`, keyed by
    finding.

    This is the idempotency check `remediation/apply.py` runs before doing
    anything: a finding that already has a live pull request must not get a
    second one. The partial unique index in migration 12 enforces the same
    rule at the database level, but this query is what produces an error a
    person can read.
    """
    if not finding_keys:
        return {}
    conn = get_connection()
    try:
        placeholders = ",".join("?" for _ in finding_keys)
        terminal = ",".join("?" for _ in TERMINAL_STATES)
        rows = conn.execute(
            f"""
            SELECT * FROM fix_applications
            WHERE scan_id = ?
              AND finding_key IN ({placeholders})
              AND state NOT IN ({terminal})
            """,
            (scan_id, *finding_keys, *TERMINAL_STATES),
        ).fetchall()
        return {row["finding_key"]: _row_to_application(row) for row in rows}
    finally:
        conn.close()


def update_fix_application_state(
    application_id: str, state: FixApplicationState
) -> None:
    """Move one application to a new state (Stage B closes PRs, Stage C
    verifies them)."""
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE fix_applications SET state = ?, updated_at = ? WHERE id = ?",
            (state.value, datetime.now(timezone.utc).isoformat(), application_id),
        )
        conn.commit()
    finally:
        conn.close()


def count_prs_for_scan(scan_id: str) -> int:
    """How many pull requests this scan has already produced -- the
    `MAX_PRS_PER_SCAN` budget's input. Failed and abandoned attempts don't
    count against it; a budget is there to stop runaway *writes*, and an
    attempt that wrote nothing is not one."""
    conn = get_connection()
    try:
        terminal = ",".join("?" for _ in TERMINAL_STATES)
        row = conn.execute(
            f"""
            SELECT COUNT(DISTINCT branch) AS n FROM fix_applications
            WHERE scan_id = ? AND branch IS NOT NULL AND state NOT IN ({terminal})
            """,
            (scan_id, *TERMINAL_STATES),
        ).fetchone()
        return row["n"] or 0
    finally:
        conn.close()


def count_prs_since(hours: int = 1) -> int:
    """Pull requests opened across all scans in the last `hours` -- the
    `MAX_PRS_PER_HOUR` budget's input. Global rather than per-user because the
    thing being rate-limited is Sentinels' write traffic to GitHub, which one
    user can exhaust for everyone."""
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    conn = get_connection()
    try:
        terminal = ",".join("?" for _ in TERMINAL_STATES)
        row = conn.execute(
            f"""
            SELECT COUNT(DISTINCT branch) AS n FROM fix_applications
            WHERE created_at >= ? AND branch IS NOT NULL AND state NOT IN ({terminal})
            """,
            (cutoff, *TERMINAL_STATES),
        ).fetchone()
        return row["n"] or 0
    finally:
        conn.close()


def write_audit(
    user_id: int | None,
    scan_id: str | None,
    finding_key: str | None,
    action: str,
    detail: str = "",
) -> None:
    """One row, every time (CLAUDE.md's remediation rule 10).

    Deliberately never raises into the caller's path on a write failure --
    but it is also never the *only* record of a successful write, so a lost
    audit row cannot silently hide a pull request that exists. `detail` is
    plain text assembled by the caller, and never contains a token.
    """
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO audit_log (user_id, scan_id, finding_key, action, detail, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (user_id, scan_id, finding_key, action, detail,
             datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
    finally:
        conn.close()


def list_audit(scan_id: str) -> list[dict]:
    """The audit trail for one scan, oldest first."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM audit_log WHERE scan_id = ? ORDER BY id", (scan_id,)
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()
