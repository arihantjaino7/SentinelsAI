"""Deterministic scoring: findings in, score/grade/counts out.

Every function here is a pure function — no network, no clock, no randomness,
no model. CLAUDE.md's rule ("scoring stays deterministic — same site, same
score, always") is enforced simply by never importing anything that could
make it otherwise.
"""
from __future__ import annotations

from models import Finding, Severity, Status, SEVERITY_PENALTY

# Score -> grade cutoffs, checked highest-first. A fixed table, not a formula,
# so "why did this get a B" always has a one-line answer: the score, and this
# table.
_GRADE_THRESHOLDS: list[tuple[int, str]] = [
    (90, "A"),
    (80, "B"),
    (70, "C"),
    (60, "D"),
]


def calculate_score(findings: list[Finding]) -> int:
    """Start at 100, subtract a penalty for every non-passing finding.

    PASS findings cost nothing — only FAIL and WARN represent an actual
    problem (see Status in models.py). Clamped to 0: a site that fails every
    check possible still gets a floor, not a confusing negative number.
    """
    penalty = sum(
        SEVERITY_PENALTY[finding.severity]
        for finding in findings
        if finding.status != Status.PASS
    )
    return max(0, 100 - penalty)


def grade_for_score(score: int) -> str:
    """Turn a 0-100 score into a letter grade using the fixed cutoffs above."""
    for threshold, grade in _GRADE_THRESHOLDS:
        if score >= threshold:
            return grade
    return "F"


def count_by_severity(findings: list[Finding]) -> dict[str, int]:
    """How many non-passing findings fall into each severity bucket.

    Every severity level is a key in the result, even at 0 — so the frontend
    can always render all five rows without first checking which keys exist.
    """
    counts = {severity.value: 0 for severity in Severity}
    for finding in findings:
        if finding.status != Status.PASS:
            counts[finding.severity.value] += 1
    return counts
