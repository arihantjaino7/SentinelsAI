"""Read/write path for `fix_plans` -- persisted FixPlans from
`POST /scans/{id}/fix/plan`.

`fix_applications` and `audit_log` (added by the same migration, `db.py`'s
`_V11_SCHEMA`) have no read/write helpers here yet -- they stay unwritten
until Stage B actually applies a plan, the same precedent `repo_files`
(V7) set: the table exists ahead of the milestone that first uses it.
"""
from __future__ import annotations

from db import get_connection
from models import FixPlan


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
