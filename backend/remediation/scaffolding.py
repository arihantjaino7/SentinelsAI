"""Two creates-only fixers for agents/repo/hygiene.py findings that have no
`file_path` at all -- they're "is X present anywhere" checks, not
line-level ones.

`ReadmeFixer` (`repo-readme-present`) -- adds a starter `README.md` when
none of hygiene.py's own recognized README names exist.

`EnvExampleFixer` (`repo-env-example-present`) -- adds `.env.example` with
every key from a committed `.env`, values blanked. Deliberately refuses to
plan anything when no `.env` exists to read keys from: inventing plausible
env-var names would be a guess dressed up as a fact, exactly what
CLAUDE.md's confidence rule forbids. (A committed `.env` is *also* a
`secret-env-committed-*` finding -- Tier 2, no Fixer in this stage -- so a
repo that trips this path already has a separate, correctly-tiered warning
about the file this fixer is reading from.)
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

from models import Finding, FixPlan
from remediation.base import Fixer
from remediation.patch import make_patch
from remediation.source import FileSource

_README_CANDIDATES = ["README.md", "readme.md", "README", "README.rst", "README.txt"]

_ENV_KEY_RE = re.compile(r"^(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=")


def _extract_env_keys(text: str) -> list[str]:
    """Pure line parse: `KEY=value` -> `"KEY"`, skipping blank lines,
    comments, and anything that doesn't look like an assignment. Order is
    preserved and duplicates are dropped."""
    keys: dict[str, None] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = _ENV_KEY_RE.match(line)
        if match:
            keys.setdefault(match.group(1), None)
    return list(keys)


class ReadmeFixer(Fixer):
    slug = "repo-readme-present"
    display_name = "Add a starter README"

    def handles(self, finding: Finding) -> bool:
        return finding.id == "repo-readme-present"

    async def plan(self, finding: Finding, files: FileSource) -> FixPlan | None:
        for name in _README_CANDIDATES:
            if await files.get(name) is not None:
                return None  # a README already exists under some recognized name

        content = (
            f"# {files.repo}\n\n"
            "_This README was scaffolded by Sentinels -- replace this with a real "
            "description of what the project does and how to run it._\n"
        )
        patch = make_patch("README.md", "create", None, content)
        return FixPlan(
            finding_key=finding.id,
            fixer_slug=self.slug,
            tier=1,
            summary="Add a starter README.md.",
            patches=[patch],
            created_at=datetime.now(timezone.utc).isoformat(),
        )


class EnvExampleFixer(Fixer):
    slug = "repo-env-example-present"
    display_name = "Add a .env.example"

    def handles(self, finding: Finding) -> bool:
        return finding.id == "repo-env-example-present"

    async def plan(self, finding: Finding, files: FileSource) -> FixPlan | None:
        env_file = await files.get(".env")
        if env_file is None:
            return None  # nothing to derive variable names from -- refuse to guess

        keys = _extract_env_keys(env_file.content)
        if not keys:
            return None

        content = "\n".join(f"{key}=" for key in keys) + "\n"
        patch = make_patch(".env.example", "create", None, content)
        return FixPlan(
            finding_key=finding.id,
            fixer_slug=self.slug,
            tier=1,
            summary=f"Add .env.example listing {len(keys)} variable name(s), values blanked.",
            patches=[patch],
            created_at=datetime.now(timezone.utc).isoformat(),
        )
