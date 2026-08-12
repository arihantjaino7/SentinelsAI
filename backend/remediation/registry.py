"""Ordered fixer registry -- the remediation-side sibling of
`agents/registry.py`. Order only matters in that the first fixer whose
`handles()` says yes wins; today no two fixers claim the same finding ID, so
in practice it doesn't matter yet.
"""
from __future__ import annotations

from models import Finding
from remediation.base import Fixer
from remediation.dockerfile import DockerRootUserFixer
from remediation.gitignore import GitignoreFixer
from remediation.scaffolding import EnvExampleFixer, ReadmeFixer
from remediation.workflows import WorkflowPinFixer

FIXERS: list[Fixer] = [
    WorkflowPinFixer(),
    GitignoreFixer(),
    ReadmeFixer(),
    EnvExampleFixer(),
    DockerRootUserFixer(),
]


def fixer_for(finding: Finding) -> Fixer | None:
    """The Fixer that handles `finding`, or `None` if there isn't one --
    which is the normal case for most findings (only tiers 1 and 2 ever
    have one; see remediation/tiers.py)."""
    for fixer in FIXERS:
        if fixer.handles(finding):
            return fixer
    return None
