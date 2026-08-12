"""The only legal ways a `fix_applications` row may change state.

`FixApplicationState` has existed since Stage A, but until now nothing said
which *order* those values are allowed to happen in — so a bug could have
marked a fix `verified` without a pull request ever merging, and the audit
trail would have recorded it as fact. This module is the one place that says
what a legal move is, and `storage/remediation.py` refuses the rest.

The happy path is a straight line:

    planned -> pr_open -> merged -> verified

`failed` and `abandoned` are reachable from anywhere, because "this attempt is
over" is always true-able: GitHub can refuse a write mid-flow, or the user can
close the pull request without merging it. Nothing leaves them — a finished
attempt stays finished, and a retry writes a *new* row (which is exactly what
the partial unique index in migration 12 permits).
"""
from __future__ import annotations

from models import FixApplicationState

# Reachable from any state: an attempt can always end.
_ALWAYS_ALLOWED = frozenset({FixApplicationState.FAILED, FixApplicationState.ABANDONED})

# Everything else, stated explicitly. An empty set means "nothing follows this".
ALLOWED_TRANSITIONS: dict[FixApplicationState, frozenset[FixApplicationState]] = {
    FixApplicationState.PLANNED: frozenset({FixApplicationState.PR_OPEN}),
    FixApplicationState.PR_OPEN: frozenset({FixApplicationState.MERGED}),
    FixApplicationState.MERGED: frozenset({FixApplicationState.VERIFIED}),
    FixApplicationState.VERIFIED: frozenset(),
    FixApplicationState.FAILED: frozenset(),
    FixApplicationState.ABANDONED: frozenset(),
}


class InvalidTransition(RuntimeError):
    """An attempt to move an application to a state it cannot reach from
    where it is. Always a bug in Sentinels, never something a user typed —
    which is why it raises rather than returning a flag."""


def transition_allowed(current: FixApplicationState, new: FixApplicationState) -> bool:
    """Is `current -> new` a legal move?

    A state to *itself* is allowed and means nothing happened: re-running a
    verification on an already-verified fix re-reads the repository and
    rewrites the same conclusion, which is not a state change and cannot
    corrupt anything.
    """
    if current == new:
        return True
    if new in _ALWAYS_ALLOWED:
        return True
    return new in ALLOWED_TRANSITIONS[current]


def check_transition(current: FixApplicationState, new: FixApplicationState) -> None:
    """Raise `InvalidTransition` unless the move is legal."""
    if not transition_allowed(current, new):
        raise InvalidTransition(
            f"A fix application cannot go from {current.value!r} to {new.value!r}."
        )
