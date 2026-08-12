"""Tests for remediation/states.py -- which moves a fix application is
allowed to make (PLAN-v5 Stage C).

The point of these is the *negative* cases: nothing may reach `verified`
without having merged first, because `verified` is Sentinels claiming it
re-observed a real repository and saw the problem gone.
"""
from __future__ import annotations

import pytest

from models import FixApplicationState as S
from remediation.states import InvalidTransition, check_transition, transition_allowed


def test_the_happy_path_is_legal_one_step_at_a_time():
    assert transition_allowed(S.PLANNED, S.PR_OPEN)
    assert transition_allowed(S.PR_OPEN, S.MERGED)
    assert transition_allowed(S.MERGED, S.VERIFIED)


@pytest.mark.parametrize("current", [S.PLANNED, S.PR_OPEN, S.FAILED, S.ABANDONED])
def test_verified_is_only_reachable_from_merged(current):
    assert not transition_allowed(current, S.VERIFIED)


def test_skipping_a_step_is_refused():
    assert not transition_allowed(S.PLANNED, S.MERGED)
    assert not transition_allowed(S.PR_OPEN, S.VERIFIED)


@pytest.mark.parametrize(
    "current", [S.PLANNED, S.PR_OPEN, S.MERGED, S.VERIFIED, S.FAILED, S.ABANDONED]
)
@pytest.mark.parametrize("ending", [S.FAILED, S.ABANDONED])
def test_an_attempt_can_always_end(current, ending):
    """GitHub can refuse a write at any point and a user can close a pull
    request without merging it, so "this attempt is over" is always sayable."""
    assert transition_allowed(current, ending)


@pytest.mark.parametrize("state", [S.VERIFIED, S.FAILED, S.ABANDONED])
def test_nothing_comes_back_from_a_finished_state(state):
    assert not transition_allowed(state, S.PR_OPEN)
    assert not transition_allowed(state, S.MERGED)


def test_a_state_to_itself_is_a_no_op_not_an_error():
    """Re-running a verification rewrites the same conclusion. That is not a
    state change and must not be treated as an illegal one."""
    assert transition_allowed(S.VERIFIED, S.VERIFIED)
    assert transition_allowed(S.PR_OPEN, S.PR_OPEN)


def test_check_transition_raises_with_both_states_named():
    with pytest.raises(InvalidTransition, match="'planned' to 'verified'"):
        check_transition(S.PLANNED, S.VERIFIED)


def test_every_state_has_an_entry():
    """A new state added to the enum without a row here would silently get a
    KeyError at runtime instead of a decision."""
    from remediation.states import ALLOWED_TRANSITIONS

    assert set(ALLOWED_TRANSITIONS) == set(S)
