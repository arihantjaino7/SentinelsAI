"""Fixer for `gitignore-present` (agents/repo/config.py's `_check_gitignore`,
the "no .gitignore file exists at all" case) -- creates a baseline
`.gitignore` covering the paths that check itself already looks for: `.env`,
private-key files, and (implicitly, since it's always safe to ignore)
dependency folders.

Creates only. If a `.gitignore` already exists but is merely incomplete,
that's the separate `gitignore-env` / `gitignore-private-keys` /
`gitignore-node-modules` findings -- none of them tier 1 (remediation/tiers.py),
so no Fixer touches an *existing* `.gitignore` in this stage.
"""
from __future__ import annotations

from datetime import datetime, timezone

from models import Finding, FixPlan
from remediation.base import Fixer
from remediation.patch import make_patch
from remediation.source import FileSource

_BASELINE_GITIGNORE = """\
# Added by Sentinels -- a starting point covering common secret and
# dependency paths. Review and extend for this project's own stack.
.env
.env.local
*.pem
*.key
id_rsa
node_modules/
__pycache__/
*.pyc
.venv/
"""


class GitignoreFixer(Fixer):
    slug = "gitignore-present"
    display_name = "Add a .gitignore"

    def handles(self, finding: Finding) -> bool:
        return finding.id == "gitignore-present"

    async def plan(self, finding: Finding, files: FileSource) -> FixPlan | None:
        existing = await files.get(".gitignore")
        if existing is not None:
            return None  # already exists -- this fixer creates only

        patch = make_patch(".gitignore", "create", None, _BASELINE_GITIGNORE)
        return FixPlan(
            finding_key=finding.id,
            fixer_slug=self.slug,
            tier=1,
            summary="Add a .gitignore covering .env, key files, and dependency folders.",
            patches=[patch],
            created_at=datetime.now(timezone.utc).isoformat(),
        )
