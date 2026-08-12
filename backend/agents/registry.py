"""Agent registry — the single list of all scanner agents.

Adding a new agent = write the class + add one line here. No other file
(routes, orchestrator, frontend) needs to change to discover the new agent.
"""
from __future__ import annotations

from agents.api_security import ApiSecurityAgent
from agents.dns_email import DNSAgent
from agents.exposure import ExposureAgent
from agents.headers import HeadersAgent
from agents.misconfig import MisconfigAgent
from agents.recon import ReconAgent
from agents.subdomain import SubdomainAgent
from agents.tls import TLSAgent
from models import AgentInfo

AGENTS = [
    HeadersAgent, ReconAgent, TLSAgent, ExposureAgent, DNSAgent,
    ApiSecurityAgent, MisconfigAgent, SubdomainAgent,
]

# Slug -> class. Built from AGENTS so it can never disagree with it, which a
# hand-written second list eventually would. PLAN-v5 Stage C needs this
# direction of lookup: a stored Finding remembers only its agent's *name*
# ("headers"), and verification has to get from that string back to the class
# to re-run it.
AGENTS_BY_NAME = {cls.name: cls for cls in AGENTS}


def agent_for(name: str):
    """The agent class registered under `name`, or `None` if no agent uses
    that slug. `None` is a normal answer — a finding saved by an older
    version of Sentinels can name an agent that no longer exists."""
    return AGENTS_BY_NAME.get(name)


def list_agents() -> list[AgentInfo]:
    """Return metadata for every registered agent, in registration order."""
    return [
        AgentInfo(
            name=cls.name,
            display_name=cls.display_name,
            purpose=cls.purpose,
            checks=cls.checks,
            category=cls.category,
        )
        for cls in AGENTS
    ]
