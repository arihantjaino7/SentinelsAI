"""Repo-agent registry -- the repo-side sibling of `agents/registry.py`.

Same rule as the URL registry: adding a new repo agent = write the class +
add one line here. No other file needs to change to discover it.
"""
from __future__ import annotations

from agents.repo.config import ConfigAgent
from agents.repo.dependencies import DependenciesAgent
from agents.repo.hygiene import HygieneAgent
from agents.repo.patterns import PatternsAgent
from agents.repo.secrets import SecretsAgent
from models import AgentInfo

AGENTS_REPO = [HygieneAgent, SecretsAgent, DependenciesAgent, ConfigAgent, PatternsAgent]


def list_repo_agents() -> list[AgentInfo]:
    """Return metadata for every registered repo agent, in registration order."""
    return [
        AgentInfo(
            name=cls.name,
            display_name=cls.display_name,
            purpose=cls.purpose,
            checks=cls.checks,
            category=cls.category,
        )
        for cls in AGENTS_REPO
    ]
