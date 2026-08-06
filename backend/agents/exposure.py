"""The Exposure agent — checks for a small, fixed list of well-known
sensitive paths being accidentally served publicly.

CLAUDE.md's scope rule sets the boundary for what this agent is allowed to
do: a couple of GET requests to specific, well-known, publicly-fetchable
paths, checked against what their real content looks like — never a
wordlist, never a guessing attack, never anything resembling brute force.
"safely" (per the roadmap) also means never echoing back whatever secrets a
real exposure might contain — see `_check_env_file` below.
"""
from __future__ import annotations

import re
from urllib.parse import urljoin

from agents.base import BaseAgent, ScanContext
from models import EvidenceKind, Finding, Severity, Status

OWASP_MISCONFIG = "A05:2021 - Security Misconfiguration"

# A real .env file is lines of KEY=VALUE. A soft-404 page (many sites return
# 200 with a custom error/landing page for ANY path) is HTML and won't match
# this shape, which is exactly the false positive this regex exists to rule out.
_ENV_LINE_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*\s*=", re.MULTILINE)


class ExposureAgent(BaseAgent):
    name = "exposure"
    display_name = "Sensitive File Exposure"
    purpose = "Requests well-known paths that, if publicly accessible, expose credentials or source history."
    checks = [
        ".env — checks whether environment variables (API keys, passwords) are readable",
        ".git/HEAD — checks whether the git repository is accessible and downloadable",
    ]
    category = "Exposure"

    async def scan(self, context: ScanContext) -> list[Finding]:
        return [
            await self._check_env_file(context),
            await self._check_git_head(context),
        ]

    async def _check_env_file(self, context: ScanContext) -> Finding:
        env_url = urljoin(context.url, "/.env")
        # follow_redirects=False on purpose: a real exposed file is served
        # directly. A server that instead 30x-redirects this path elsewhere
        # is telling us the file isn't reachable here — following the
        # redirect would just have us grade a different page entirely.
        response = await context.client.get(env_url, follow_redirects=False)

        content_type = response.headers.get("content-type", "").lower()
        looks_real = (
            response.status_code == 200
            and "html" not in content_type
            and _ENV_LINE_RE.search(response.text)
        )

        if looks_real:
            match_count = len(_ENV_LINE_RE.findall(response.text))
            # Same no-echo rule applies to the structured evidence item as to
            # the flat `evidence` string above: request + status + count
            # only, never the response body.
            evidence_text = (
                f"GET {env_url} -> 200, {match_count} KEY=VALUE-shaped "
                "line(s) found (content withheld — see description)."
            )
            return Finding(
                id="env-file-exposed",
                title=".env file is publicly accessible",
                category="Exposure",
                severity=Severity.CRITICAL,
                status=Status.FAIL,
                owasp=OWASP_MISCONFIG,
                # Deliberately NOT echoing the actual file content here.
                # Doing so would leak the very secrets this finding warns
                # about, straight into our own report.
                evidence=evidence_text,
                description=(
                    ".env files commonly hold database passwords, API keys, "
                    "and other credentials in plain text. Anyone who "
                    "requests this path directly gets those secrets exactly "
                    "as-is."
                ),
                remediation=(
                    "Remove .env from the web server's public document root "
                    "entirely — it should never be reachable there — and "
                    "rotate every credential it contained."
                ),
                evidence_items=[
                    self.evidence(EvidenceKind.REQUEST, ".env request", evidence_text)
                ],
            )
        request_text = f"GET {env_url} -> {response.status_code}"
        return Finding(
            id="env-file-exposed",
            title=".env file is not publicly accessible",
            category="Exposure",
            severity=Severity.INFO,
            status=Status.PASS,
            owasp=OWASP_MISCONFIG,
            evidence=request_text,
            evidence_items=[
                self.evidence(EvidenceKind.REQUEST, ".env request", request_text)
            ],
        )

    async def _check_git_head(self, context: ScanContext) -> Finding:
        git_head_url = urljoin(context.url, "/.git/HEAD")
        response = await context.client.get(git_head_url, follow_redirects=False)

        # A real git HEAD file's content is exactly "ref: refs/heads/<branch>"
        # (or a bare 40-char commit hash in "detached HEAD" state) — a very
        # specific shape a soft-404 HTML page won't accidentally match.
        looks_real = (
            response.status_code == 200
            and response.text.strip().startswith("ref:")
        )

        if looks_real:
            evidence_text = f"GET {git_head_url} -> 200, content matches a real git HEAD file."
            return Finding(
                id="git-directory-exposed",
                title=".git directory is publicly accessible",
                category="Exposure",
                severity=Severity.HIGH,
                status=Status.FAIL,
                owasp=OWASP_MISCONFIG,
                evidence=evidence_text,
                description=(
                    "A publicly reachable .git directory usually lets an "
                    "attacker reconstruct the site's entire source history — "
                    "including anything ever committed, even secrets long "
                    "since removed from the current code."
                ),
                remediation=(
                    "Block access to .git entirely at the web server level — "
                    "it should never be inside the public document root."
                ),
                evidence_items=[
                    self.evidence(EvidenceKind.REQUEST, ".git/HEAD request", evidence_text)
                ],
            )
        request_text = f"GET {git_head_url} -> {response.status_code}"
        return Finding(
            id="git-directory-exposed",
            title=".git directory is not publicly accessible",
            category="Exposure",
            severity=Severity.INFO,
            status=Status.PASS,
            owasp=OWASP_MISCONFIG,
            evidence=request_text,
            evidence_items=[
                self.evidence(EvidenceKind.REQUEST, ".git/HEAD request", request_text)
            ],
        )
