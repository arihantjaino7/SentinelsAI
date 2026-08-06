"""The Recon agent — fingerprints what a site is built with.

Two passive checks: a generator meta tag in the homepage's HTML (a common,
often accidental, way sites announce their exact CMS/version), and a
robots.txt fetch, checked against a short list of sensitive-looking path
keywords. Both are single GET requests to public paths — nothing here
guesses, brute-forces, or requests a path that isn't meant to be publicly
fetchable.
"""
from __future__ import annotations

from urllib.parse import urljoin

from bs4 import BeautifulSoup

from agents.base import BaseAgent, ScanContext
from models import EvidenceKind, Finding, Severity, Status

OWASP_INFO_DISCLOSURE = "A05:2021 - Security Misconfiguration"

# Path fragments that make a disallowed robots.txt entry worth a second look.
# Deliberately short and not exhaustive — this is a quick, honest signal, not
# an exhaustive wordlist scan (which would cross into the kind of probing this
# project doesn't do).
_SENSITIVE_KEYWORDS = (
    "admin", "login", "wp-admin", "backup", "config", "secret", ".env", "private",
)


class ReconAgent(BaseAgent):
    name = "recon"
    display_name = "Reconnaissance"
    purpose = "Looks for information the site leaks about itself that attackers use to find known vulnerabilities."
    checks = [
        "Generator meta tag — reveals the CMS or framework name and exact version",
        "robots.txt — flags Disallow entries with admin, login, backup, or config keywords",
    ]
    category = "Recon"

    async def scan(self, context: ScanContext) -> list[Finding]:
        return [
            await self._check_generator(context),
            await self._check_robots_txt(context),
        ]

    async def _check_generator(self, context: ScanContext) -> Finding:
        response = await context.client.get(context.url, follow_redirects=True)
        soup = BeautifulSoup(response.text, "html.parser")
        tag = soup.find("meta", attrs={"name": "generator"})
        content = tag.get("content") if tag else None

        if content:
            snippet = f'<meta name="generator" content="{content}">'
            return Finding(
                id="generator-meta-exposed",
                title="Generator meta tag reveals platform/version",
                category="Recon",
                severity=Severity.LOW,
                status=Status.WARN,
                owasp=OWASP_INFO_DISCLOSURE,
                evidence=snippet,
                description=(
                    "The homepage announces its exact platform and version. "
                    "That's a shortcut for an attacker looking for known CVEs "
                    "affecting that specific version."
                ),
                remediation=(
                    "Remove or blank the generator meta tag in your CMS/"
                    "framework's settings."
                ),
                evidence_items=[
                    self.evidence(EvidenceKind.HTML_SNIPPET, "Generator meta tag", snippet, "text/html")
                ],
            )
        no_tag_text = 'No <meta name="generator"> tag in the response HTML.'
        return Finding(
            id="generator-meta-exposed",
            title="No generator meta tag found",
            category="Recon",
            severity=Severity.INFO,
            status=Status.PASS,
            owasp=OWASP_INFO_DISCLOSURE,
            evidence=no_tag_text,
            evidence_items=[
                self.evidence(EvidenceKind.HTML_SNIPPET, "Generator meta tag", no_tag_text, "text/html")
            ],
        )

    async def _check_robots_txt(self, context: ScanContext) -> Finding:
        robots_url = urljoin(context.url, "/robots.txt")
        response = await context.client.get(robots_url, follow_redirects=True)

        if response.status_code != 200:
            request_text = f"GET {robots_url} -> {response.status_code}"
            return Finding(
                id="robots-txt-sensitive-paths",
                title="No robots.txt found",
                category="Recon",
                severity=Severity.INFO,
                status=Status.PASS,
                evidence=request_text,
                evidence_items=[
                    self.evidence(EvidenceKind.REQUEST, "robots.txt request", request_text)
                ],
            )

        disallowed = [
            line.split(":", 1)[1].strip()
            for line in response.text.splitlines()
            if line.strip().lower().startswith("disallow:")
        ]
        disallowed = [path for path in disallowed if path]  # "Disallow:" (empty) means allow-all
        # robots.txt commonly repeats the same path under several User-agent
        # blocks (one for Googlebot, one for Bingbot, ...) — dict.fromkeys
        # dedupes while keeping first-seen order, so evidence doesn't show
        # the same path three times over.
        disallowed = list(dict.fromkeys(disallowed))

        suspicious = [
            path for path in disallowed
            if any(keyword in path.lower() for keyword in _SENSITIVE_KEYWORDS)
        ]

        if suspicious:
            evidence_text = f"Disallowed paths: {', '.join(suspicious)}"
            return Finding(
                id="robots-txt-sensitive-paths",
                title="robots.txt discloses sensitive-looking paths",
                category="Recon",
                severity=Severity.LOW,
                status=Status.WARN,
                evidence=evidence_text,
                description=(
                    "robots.txt only asks well-behaved crawlers not to index "
                    "these paths — it doesn't block anyone from requesting "
                    "them directly. Listing them here is effectively a map "
                    "of what you'd rather people not look at."
                ),
                remediation=(
                    "Don't rely on robots.txt to hide sensitive paths; "
                    "restrict access to them properly (authentication, "
                    "network rules) instead."
                ),
                evidence_items=[
                    self.evidence(EvidenceKind.HTML_SNIPPET, "robots.txt Disallow entries", evidence_text, "text/plain")
                ],
            )
        clean_text = (
            f"{len(disallowed)} disallowed path(s) listed."
            if disallowed else
            "robots.txt present with no Disallow entries."
        )
        return Finding(
            id="robots-txt-sensitive-paths",
            title="robots.txt present, no obviously sensitive paths disclosed",
            category="Recon",
            severity=Severity.INFO,
            status=Status.PASS,
            evidence=clean_text,
            evidence_items=[
                self.evidence(EvidenceKind.HTML_SNIPPET, "robots.txt Disallow entries", clean_text, "text/plain")
            ],
        )
