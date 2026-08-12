"""Fixer for `ci-unpinned-action-*` (agents/repo/config.py's `_check_workflow`):
pins a GitHub Actions `uses: owner/repo@ref` line to the immutable commit SHA
`ref` currently resolves to.

Split in two, per PLAN-v5.md conflict #3 ("Tag -> SHA resolution needs the
network"):

- `rewrite_uses_line` -- a pure string rewrite, offline-testable with no
  client and no finding at all.
- `WorkflowPinFixer.plan` -- re-reads the file at `finding.line`, re-parses
  the `uses:` reference from the *current* text (never trusts the finding's
  possibly-stale `evidence` string), resolves that ref's SHA over the
  network, and calls the pure rewrite above.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

from models import Finding, FixPlan
from remediation.base import Fixer
from remediation.patch import make_patch
from remediation.source import FileSource

_USES_RE = re.compile(r"uses:\s*([\w.\-]+/[\w.\-]+)@([\w.\-]+)")
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def rewrite_uses_line(line: str, ref: str, sha: str) -> str | None:
    """Replace `@{ref}` with `@{sha}` on one `uses:` line, preserving
    indentation and the line ending exactly. A trailing `# {ref}` comment is
    added (or replaces any existing trailing comment) so a human reading the
    pinned line can still see which tag it came from.

    Returns `None` if the line doesn't contain `uses:` followed by exactly
    `@{ref}` -- meaning the line has already changed since the finding was
    produced, and rewriting it would be a guess.
    """
    if "uses:" not in line:
        return None
    marker = f"@{ref}"
    idx = line.find(marker)
    if idx == -1:
        return None

    before = line[:idx]
    after = line[idx + len(marker):]

    line_ending = ""
    if after.endswith("\r\n"):
        line_ending, after = "\r\n", after[:-2]
    elif after.endswith("\n"):
        line_ending, after = "\n", after[:-1]

    # Drop any pre-existing trailing comment before appending our own --
    # avoids "# v2 # v2" if this were ever run twice against the same line.
    rest = after.split("#", 1)[0].rstrip()

    return f"{before}@{sha}{rest}  # {ref}{line_ending}"


class WorkflowPinFixer(Fixer):
    slug = "ci-unpinned-action"
    display_name = "Pin GitHub Action to a commit SHA"

    def handles(self, finding: Finding) -> bool:
        return finding.id.startswith("ci-unpinned-action-")

    async def plan(self, finding: Finding, files: FileSource) -> FixPlan | None:
        if not finding.file_path or not finding.line:
            return None

        source = await files.get(finding.file_path)
        if source is None:
            return None  # the workflow file is gone since the scan ran

        lines = source.content.splitlines(keepends=True)
        if finding.line < 1 or finding.line > len(lines):
            return None
        line = lines[finding.line - 1]

        match = _USES_RE.search(line)
        if match is None:
            return None  # line no longer names an action -- edited since

        action_repo, ref = match.group(1), match.group(2)
        if _SHA_RE.match(ref):
            return None  # already pinned

        owner, repo = action_repo.split("/", 1)
        sha = await files.resolve_sha(owner, repo, ref)
        if sha is None:
            return None  # couldn't resolve -- refuse to guess rather than write a wrong SHA

        new_line = rewrite_uses_line(line, ref, sha)
        if new_line is None or new_line == line:
            return None

        new_lines = list(lines)
        new_lines[finding.line - 1] = new_line
        new_content = "".join(new_lines)

        patch = make_patch(finding.file_path, "modify", source, new_content)
        return FixPlan(
            finding_key=finding.id,
            fixer_slug=self.slug,
            tier=1,
            summary=f"Pin {action_repo}@{ref} to commit {sha[:12]}.",
            patches=[patch],
            created_at=datetime.now(timezone.utc).isoformat(),
        )
