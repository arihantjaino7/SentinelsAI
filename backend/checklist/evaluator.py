"""Pure checklist evaluation — findings in, ChecklistItems + readiness out.

No network, no clock, no LLM. Same discipline as scoring.py: given the same
findings, you always get the same checklist. This is verified by the M9
acceptance criterion: "scan the same site twice → identical checklist output."
"""
from __future__ import annotations

from models import ChecklistItem, Finding
from checklist.rules import ChecklistRule, RULES


def evaluate(findings: list[Finding], rules: list[ChecklistRule] = RULES) -> list[ChecklistItem]:
    """Turn a finished scan's findings into a full deployment checklist.

    `rules` defaults to the URL side's `RULES` so every existing caller keeps
    working untouched; a repo scan passes `checklist.repo_rules.REPO_RULES`
    instead (PLAN-v3 R9). Safe as a default value here because it's never
    mutated -- only iterated -- unlike the classic `def f(x=[])` trap.
    """
    items = []
    for rule in rules:
        state, explanation, suggested_fix = rule.evaluate(findings)
        items.append(ChecklistItem(
            item_key=rule.key,
            title=rule.title,
            tier=rule.tier,
            state=state,
            explanation=explanation,
            suggested_fix=suggested_fix,
            agent=rule.agent,
        ))
    return items


def compute_readiness(
    checklist: list[ChecklistItem], rules: list[ChecklistRule] = RULES
) -> tuple[int, str]:
    """Derive a readiness score (0-100) and deployment status from the checklist.

    readiness_score — percentage of auto-verified items in "pass" state.
    deployment_status:
      "blocked" — any blocking auto item has failed (critical exposure, no HTTPS)
      "caution" — no blockers but some auto/inferred items are failing or warning
      "ready"   — all auto and inferred items are passing

    Self-attested items are excluded from the score; their answers don't affect
    the objective readiness calculation. `rules` must be the same rule set that
    produced `checklist` -- it's only consulted for each item's `blocking` flag.
    """
    rule_by_key = {r.key: r for r in rules}

    auto_items = [c for c in checklist if c.tier == "auto"]
    auto_inferred = [c for c in checklist if c.tier in ("auto", "inferred")]

    # Readiness score = % of auto items that passed
    if auto_items:
        passing = sum(1 for c in auto_items if c.state == "pass")
        readiness_score = round(passing / len(auto_items) * 100)
    else:
        readiness_score = 100

    # Deployment status
    for item in auto_items:
        rule = rule_by_key.get(item.item_key)
        if rule and rule.blocking and item.state == "fail":
            return readiness_score, "blocked"

    for item in auto_inferred:
        if item.state in ("fail", "warn"):
            return readiness_score, "caution"

    return readiness_score, "ready"
