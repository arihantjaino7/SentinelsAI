"""Detect what actually serves a linked repository's site -- the piece
`remediation/headers_fix.py`'s `SecurityHeaderFixer` needs before it can
decide *where* a missing security header should be added (PLAN-v5 Stage D).

Scoped to exactly two targets, per the stage's own scope decision: Vercel
(`vercel.json`) and Next.js (`next.config.{js,ts,mjs}`). Anything else comes
back as `None` -- an honest "I don't recognize this stack", never a guess.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from remediation.source import FileSource, SourceFile

# Checked in this order: Vercel first, even when a Next.js config also
# exists. Platform-level headers apply regardless of framework, so on a
# Vercel deployment the edge network -- not next.config.ts -- is the layer
# actually setting the response header.
NEXT_CONFIG_CANDIDATES: tuple[str, ...] = (
    "next.config.ts",
    "next.config.js",
    "next.config.mjs",
)
VERCEL_CONFIG_PATH = "vercel.json"


class StackKind(str, Enum):
    VERCEL = "vercel"
    NEXTJS = "nextjs"


@dataclass
class StackResult:
    kind: StackKind
    path: str                      # the config file's actual path
    existing: SourceFile | None    # its current content, if it exists yet


async def detect_stack(files: FileSource) -> StackResult | None:
    """Probe for a recognized stack, or `None` if nothing matched.

    A `StackResult` with `existing=None` still means "detected" for
    Next.js -- there is no config file *yet*, but nothing else in the repo
    claims this site either, so creating one is the right move. Vercel has
    no such case: `vercel.json` either exists or Vercel isn't the answer.
    """
    vercel = await files.get(VERCEL_CONFIG_PATH)
    if vercel is not None:
        return StackResult(kind=StackKind.VERCEL, path=VERCEL_CONFIG_PATH, existing=vercel)

    for candidate in NEXT_CONFIG_CANDIDATES:
        found = await files.get(candidate)
        if found is not None:
            return StackResult(kind=StackKind.NEXTJS, path=candidate, existing=found)

    package_json = await files.get("package.json")
    if package_json is not None and '"next"' in package_json.content:
        # A Next.js project with no config file at all yet -- creating one
        # is still the right move, at the default filename.
        return StackResult(kind=StackKind.NEXTJS, path=NEXT_CONFIG_CANDIDATES[0], existing=None)

    return None
