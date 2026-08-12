"""The contract every deterministic fixer must satisfy -- the remediation-side
sibling of `agents/base.py` / `agents/repo/base.py`.

A `Fixer` never invents a patch. `plan()` is plain, deterministic Python
working off content this process fetched itself through `FileSource`
(CLAUDE.md's remediation rule 1: "The LLM never generates a security
patch"). Given the same finding and the same repo state, it always produces
the same `FixPlan` -- or the same `None`, when there's nothing left to fix.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from models import Finding, FixPlan
from remediation.source import FileSource


class Fixer(ABC):
    slug: str = "base"
    display_name: str = ""

    @abstractmethod
    def handles(self, finding: Finding) -> bool:
        """True if this fixer knows how to address `finding.id`."""
        raise NotImplementedError

    @abstractmethod
    async def plan(self, finding: Finding, files: FileSource) -> FixPlan | None:
        """Produce a FixPlan, or `None` if -- having looked at the repo's
        current state through `files` -- there is nothing left to do
        (already fixed since the scan ran, the file is gone, or something
        this fixer needs can't be safely resolved). `None` is a normal,
        honest answer here, never an error."""
        raise NotImplementedError
