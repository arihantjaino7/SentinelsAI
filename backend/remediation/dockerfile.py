"""Fixer for `docker-root-user-*` (agents/repo/config.py's `_check_dockerfile`)
-- inserts a non-root `USER` before the container's entrypoint. Tier 2
(review-required): the base-image detection below is a heuristic, not a
certainty, so this always needs a human to look at the diff before it merges.

PLAN-v5.md is explicit that this must not trust the finding's own
`line=1` placeholder -- the insertion point is found fresh, before the
*last* `CMD`/`ENTRYPOINT` instruction in the file (a multi-stage Dockerfile
can have several; only the final stage's entrypoint matters for the image
that actually ships).
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

from models import Finding, FixPlan
from remediation.base import Fixer
from remediation.patch import make_patch
from remediation.source import FileSource

_FROM_RE = re.compile(r"^\s*FROM\s+([^\s]+)", re.IGNORECASE | re.MULTILINE)
_USER_RE = re.compile(r"^\s*USER\s+", re.IGNORECASE)
_ENTRYPOINT_RE = re.compile(r"^\s*(CMD|ENTRYPOINT)\b", re.IGNORECASE)

# Keyed by the base-image family this Dockerfile's last FROM looks like.
# Alpine's BusyBox `adduser`/`addgroup` take different flags than the
# `useradd` most other common bases (Debian, Ubuntu, the official
# python/node images) ship -- getting this wrong produces a Dockerfile that
# doesn't build, which is worse than not fixing it at all.
_USER_BLOCK_BY_FAMILY = {
    "alpine": "RUN addgroup -S appgroup && adduser -S appuser -G appgroup\nUSER appuser\n",
    "debian": "RUN useradd --create-home --shell /usr/sbin/nologin appuser\nUSER appuser\n",
}


def _detect_family(dockerfile_text: str) -> str:
    """Guess a base-image family from the *last* FROM line -- the one that
    actually determines the final image in a multi-stage build. Defaults to
    "debian" (the `useradd` family): it's the shape most non-Alpine base
    images share, including the official `python`/`node` images, which are
    a safer default than assuming BusyBox tooling that usually isn't there.
    """
    images = _FROM_RE.findall(dockerfile_text)
    last_image = images[-1] if images else ""
    # Checked against the whole reference, tag included -- "alpine" almost
    # always shows up in the tag (python:3.12-alpine), not the image name.
    return "alpine" if "alpine" in last_image.lower() else "debian"


class DockerRootUserFixer(Fixer):
    slug = "docker-root-user"
    display_name = "Add a non-root USER"

    def handles(self, finding: Finding) -> bool:
        return finding.id.startswith("docker-root-user-")

    async def plan(self, finding: Finding, files: FileSource) -> FixPlan | None:
        if not finding.file_path:
            return None

        source = await files.get(finding.file_path)
        if source is None:
            return None  # the Dockerfile is gone since the scan ran

        lines = source.content.splitlines(keepends=True)
        if any(_USER_RE.match(line) for line in lines):
            return None  # already fixed since the scan ran

        insert_at = None
        for i, line in enumerate(lines):
            if _ENTRYPOINT_RE.match(line):
                insert_at = i  # keep updating -- we want the LAST match, not the first
        if insert_at is None:
            insert_at = len(lines)  # no CMD/ENTRYPOINT at all -- append at the end

        family = _detect_family(source.content)
        block = _USER_BLOCK_BY_FAMILY[family]

        new_lines = lines[:insert_at] + [block] + lines[insert_at:]
        new_content = "".join(new_lines)

        patch = make_patch(finding.file_path, "modify", source, new_content)
        return FixPlan(
            finding_key=finding.id,
            fixer_slug=self.slug,
            tier=2,
            summary="Add a non-root USER before the container's entrypoint.",
            patches=[patch],
            created_at=datetime.now(timezone.utc).isoformat(),
        )
