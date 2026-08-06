"""The Headers agent — the first agent that does real work.

Checks a small set of security-relevant HTTP response headers on the target
URL and turns the presence/absence of each into a `Finding`. This is a single
passive GET request; nothing here writes, guesses, or brute-forces anything.
"""
from __future__ import annotations

import httpx

from agents.base import BaseAgent, ScanContext
from models import EvidenceKind, Finding, Severity, Status

OWASP_MISCONFIG = "A05:2021 - Security Misconfiguration"


class HeadersAgent(BaseAgent):
    """Fetches the target once and inspects its response headers."""

    name = "headers"
    display_name = "Security Headers"
    purpose = "Checks whether the server sends the four most important security-related HTTP response headers."
    checks = [
        "Content-Security-Policy — restricts what scripts/styles/frames the browser will load",
        "Strict-Transport-Security — prevents downgrade attacks from HTTPS to HTTP",
        "X-Content-Type-Options — stops browsers from guessing a response's content type",
        "X-Frame-Options — blocks the page from being embedded invisibly in another site",
    ]
    category = "Headers"

    async def scan(self, context: ScanContext) -> list[Finding]:
        # follow_redirects: the header we care about might only be set on the
        # final page, not on an intermediate "http -> https" redirect hop.
        response = await context.client.get(context.url, follow_redirects=True)
        headers = response.headers

        return [
            self._check(
                headers,
                "content-security-policy",
                id_="missing-csp",
                title="Content-Security-Policy",
                severity=Severity.HIGH,
                description=(
                    "Without a CSP, the browser has no allow-list for scripts, "
                    "styles, or frames — a successful injection (e.g. stored XSS) "
                    "runs with full trust instead of being blocked by the browser "
                    "itself before it executes."
                ),
                remediation=(
                    "Add a Content-Security-Policy header, starting from a "
                    "restrictive default-src 'self' and widening only for sources "
                    "you actually use."
                ),
            ),
            self._check(
                headers,
                "strict-transport-security",
                id_="missing-hsts",
                title="Strict-Transport-Security (HSTS)",
                severity=Severity.HIGH,
                description=(
                    "Without HSTS, a user's first visit — or any visit after "
                    "clearing cookies — can be silently downgraded to plain HTTP "
                    "by an on-path attacker, who then reads or modifies traffic "
                    "before the browser ever insists on encryption."
                ),
                remediation=(
                    "Add Strict-Transport-Security: max-age=31536000; "
                    "includeSubDomains once the site is served over HTTPS "
                    "everywhere."
                ),
            ),
            self._check(
                headers,
                "x-content-type-options",
                id_="missing-x-content-type-options",
                title="X-Content-Type-Options",
                severity=Severity.MEDIUM,
                description=(
                    "Without 'nosniff', some browsers guess a response's content "
                    "type from its bytes rather than trusting the declared "
                    "Content-Type — which can turn an uploaded 'image' into "
                    "executed script in the browser."
                ),
                remediation="Add X-Content-Type-Options: nosniff.",
            ),
            self._check(
                headers,
                "x-frame-options",
                id_="missing-x-frame-options",
                title="X-Frame-Options",
                severity=Severity.MEDIUM,
                description=(
                    "Without this header (or an equivalent frame-ancestors in a "
                    "CSP), the page can be loaded inside an invisible <iframe> on "
                    "another site and tricked into accepting clicks meant for "
                    "something else — clickjacking."
                ),
                remediation=(
                    "Add X-Frame-Options: DENY, or SAMEORIGIN if framing your own "
                    "site is genuinely required."
                ),
            ),
        ]

    def _check(
        self,
        headers: httpx.Headers,
        header_name: str,
        *,
        id_: str,
        title: str,
        severity: Severity,
        description: str = "",
        remediation: str = "",
    ) -> Finding:
        """Build a PASS or FAIL Finding for one header, uniformly."""
        value = headers.get(header_name)
        if value is None:
            evidence_text = f"No '{header_name}' header in the response."
            return Finding(
                id=id_,
                title=f"{title} header not set",
                category="Headers",
                severity=severity,
                status=Status.FAIL,
                owasp=OWASP_MISCONFIG,
                evidence=evidence_text,
                description=description,
                remediation=remediation,
                evidence_items=[
                    self.evidence(EvidenceKind.RESPONSE_HEADERS, "Response headers", evidence_text)
                ],
            )
        evidence_text = f"{header_name}: {value}"
        return Finding(
            id=id_,
            title=f"{title} header present",
            category="Headers",
            severity=Severity.INFO,
            status=Status.PASS,
            owasp=OWASP_MISCONFIG,
            evidence=evidence_text,
            evidence_items=[
                self.evidence(EvidenceKind.RESPONSE_HEADERS, "Response headers", evidence_text)
            ],
        )
