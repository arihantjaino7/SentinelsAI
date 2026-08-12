"""Tests for the slug -> class lookups on both agent registries (PLAN-v5
Stage C).

A stored `Finding` remembers only its agent's *name*. Verification has to get
from that string back to something runnable, and get `None` — not a crash —
when the string names nothing.
"""
from __future__ import annotations

from agents.registry import AGENTS, AGENTS_BY_NAME, agent_for
from agents.repo_registry import AGENTS_REPO, AGENTS_REPO_BY_NAME, repo_agent_for


def test_every_registered_agent_is_findable_by_its_slug():
    for cls in AGENTS:
        assert agent_for(cls.name) is cls
    for cls in AGENTS_REPO:
        assert repo_agent_for(cls.name) is cls


def test_the_lookups_cover_every_registered_agent():
    """Derived from the lists rather than written out twice, so the two can
    never drift apart."""
    assert len(AGENTS_BY_NAME) == len(AGENTS)
    assert len(AGENTS_REPO_BY_NAME) == len(AGENTS_REPO)


def test_an_unknown_slug_is_none_not_an_error():
    assert agent_for("repo-config") is None       # a repo agent, on the URL registry
    assert repo_agent_for("headers") is None      # and the other way around
    assert agent_for("") is None
    assert repo_agent_for("agent-that-never-existed") is None
