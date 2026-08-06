"""The DNS agent — checks whether this domain's email can be spoofed.

Reads two public DNS TXT records: SPF (on the domain itself) and DMARC (on
`_dmarc.<domain>`). Both are ordinary public DNS lookups — the exact same
reads any real mail server performs before deciding whether to accept a
message claiming to be from this domain.
"""
from __future__ import annotations

import asyncio
import re
from urllib.parse import urlsplit

import dns.resolver

from agents.base import BaseAgent, ScanContext
from models import EvidenceKind, Finding, Severity, Status

OWASP_MISCONFIG = "A05:2021 - Security Misconfiguration"

_POLICY_RE = re.compile(r"p\s*=\s*(\w+)", re.IGNORECASE)


def _query_txt(name: str) -> list[str]:
    """Blocking dnspython lookup — run via asyncio.to_thread, the same
    pattern as A8's TLS handshake (dnspython has no async API either).

    NXDOMAIN ("this name doesn't exist") and NoAnswer ("it exists, but has
    no TXT records") both mean "nothing here" for our purposes — a totally
    normal, expected outcome for a domain with no SPF/DMARC configured, not
    an error condition.

    We use Google's public resolver (8.8.8.8) explicitly because the system
    resolver on some machines (VPN, corporate DHCP) points at internal DNS
    servers that refuse external lookups and time out.
    """
    resolver = dns.resolver.Resolver(configure=False)
    resolver.nameservers = ["8.8.8.8", "1.1.1.1"]
    try:
        answer = resolver.resolve(name, "TXT")
    except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer):
        return []
    return [
        "".join(segment.decode("utf-8", errors="replace") for segment in rdata.strings)
        for rdata in answer
    ]


def _find_record(records: list[str], prefix: str) -> str | None:
    """A domain's TXT records are often a pile of unrelated verification
    strings (Google, Facebook, Stripe, ...) alongside the one that matters —
    this finds the one actually starting with the prefix we're looking for.
    """
    for record in records:
        if record.strip().lower().startswith(prefix.lower()):
            return record.strip()
    return None


class DNSAgent(BaseAgent):
    name = "dns"
    display_name = "DNS / Email Security"
    purpose = "Reads public DNS TXT records to check whether the domain is protected against email spoofing."
    checks = [
        "SPF record — lists which servers are authorized to send email as this domain",
        "DMARC record — sets the policy for what to do when SPF fails (quarantine or reject)",
    ]
    category = "DNS"

    async def scan(self, context: ScanContext) -> list[Finding]:
        hostname = urlsplit(context.url).hostname
        return [
            await self._check_spf(hostname),
            await self._check_dmarc(hostname),
        ]

    async def _check_spf(self, hostname: str) -> Finding:
        records = await asyncio.to_thread(_query_txt, hostname)
        spf = _find_record(records, "v=spf1")

        if spf is None:
            no_spf_text = f"No TXT record starting with 'v=spf1' at {hostname}."
            return Finding(
                id="spf-record",
                title="No SPF record found",
                category="DNS",
                severity=Severity.HIGH,
                status=Status.FAIL,
                owasp=OWASP_MISCONFIG,
                evidence=no_spf_text,
                description=(
                    "Without SPF, receiving mail servers have no list of "
                    "which servers are authorized to send email as this "
                    "domain — anyone can send a forged message claiming to "
                    "be from it, and many mail servers will accept it."
                ),
                remediation=(
                    "Publish a TXT record on the domain listing every server "
                    "authorized to send its mail, e.g. "
                    "'v=spf1 include:_spf.example.com -all'."
                ),
                evidence_items=[
                    self.evidence(EvidenceKind.DNS_RECORD, f"TXT records at {hostname}", no_spf_text)
                ],
            )

        spf_evidence = [self.evidence(EvidenceKind.DNS_RECORD, f"SPF record at {hostname}", spf)]
        tokens = spf.split()

        if any(token.lower().startswith("redirect=") for token in tokens):
            return Finding(
                id="spf-record",
                title="SPF record delegates enforcement (redirect=)",
                category="DNS",
                severity=Severity.INFO,
                status=Status.PASS,
                owasp=OWASP_MISCONFIG,
                evidence=spf,
                evidence_items=spf_evidence,
            )

        all_token = next(
            (t for t in tokens if t.lower().lstrip("+-~?") == "all"), None
        )

        if all_token is None:
            return Finding(
                id="spf-record",
                title="SPF record has no enforcement mechanism",
                category="DNS",
                severity=Severity.MEDIUM,
                status=Status.WARN,
                owasp=OWASP_MISCONFIG,
                evidence=spf,
                description=(
                    "The record has no 'all' mechanism, so it never actually "
                    "states what to do about mail from servers it doesn't list."
                ),
                remediation=(
                    "End the SPF record with '-all' (or at least '~all') so "
                    "unauthorized senders are explicitly rejected or flagged."
                ),
                evidence_items=spf_evidence,
            )

        # RFC 7208 qualifiers: '-' fail, '~' softfail, '?' neutral, '+' pass
        # (or no symbol at all, which defaults to '+'). '-'/'~' both mean
        # real enforcement; '?' and '+' both mean "no actual protection."
        qualifier = all_token[0] if all_token[0] in "+-~?" else "+"

        if qualifier == "+":
            return Finding(
                id="spf-record",
                title="SPF record allows any server to send mail (+all)",
                category="DNS",
                severity=Severity.HIGH,
                status=Status.FAIL,
                owasp=OWASP_MISCONFIG,
                evidence=spf,
                description=(
                    "'+all' explicitly authorizes every server on the "
                    "internet to send mail as this domain — SPF is present "
                    "but provides no protection at all."
                ),
                remediation="Replace '+all' with '-all' so only the listed servers are authorized.",
                evidence_items=spf_evidence,
            )
        if qualifier == "?":
            return Finding(
                id="spf-record",
                title="SPF record uses a neutral qualifier (?all)",
                category="DNS",
                severity=Severity.MEDIUM,
                status=Status.WARN,
                owasp=OWASP_MISCONFIG,
                evidence=spf,
                description=(
                    "'?all' explicitly declares 'no opinion' about unlisted "
                    "senders, which functions like having no policy at all."
                ),
                remediation="Replace '?all' with '-all' or '~all' so unauthorized senders are actually flagged.",
                evidence_items=spf_evidence,
            )
        return Finding(
            id="spf-record",
            title="SPF record present with enforcement",
            category="DNS",
            severity=Severity.INFO,
            status=Status.PASS,
            owasp=OWASP_MISCONFIG,
            evidence=spf,
            evidence_items=spf_evidence,
        )

    async def _check_dmarc(self, hostname: str) -> Finding:
        records = await asyncio.to_thread(_query_txt, f"_dmarc.{hostname}")
        dmarc = _find_record(records, "v=DMARC1")

        if dmarc is None:
            no_dmarc_text = f"No TXT record starting with 'v=DMARC1' at _dmarc.{hostname}."
            return Finding(
                id="dmarc-record",
                title="No DMARC record found",
                category="DNS",
                severity=Severity.HIGH,
                status=Status.FAIL,
                owasp=OWASP_MISCONFIG,
                evidence=no_dmarc_text,
                description=(
                    "Without DMARC, there's no policy telling receiving mail "
                    "servers what to do with a message that fails SPF — and "
                    "no reports telling the domain owner that spoofing is "
                    "being attempted at all."
                ),
                remediation=(
                    "Publish a DMARC TXT record at _dmarc.<domain>, starting "
                    "with monitoring ('p=none') and moving to "
                    "'p=quarantine' or 'p=reject' once legitimate mail is "
                    "confirmed to pass."
                ),
                evidence_items=[
                    self.evidence(EvidenceKind.DNS_RECORD, f"TXT records at _dmarc.{hostname}", no_dmarc_text)
                ],
            )

        dmarc_evidence = [self.evidence(EvidenceKind.DNS_RECORD, f"DMARC record at _dmarc.{hostname}", dmarc)]
        policy_match = _POLICY_RE.search(dmarc)
        policy = policy_match.group(1).lower() if policy_match else None

        if policy is None or policy == "none":
            return Finding(
                id="dmarc-record",
                title="DMARC policy is not enforced (p=none)",
                category="DNS",
                severity=Severity.MEDIUM,
                status=Status.WARN,
                owasp=OWASP_MISCONFIG,
                evidence=dmarc,
                description=(
                    "'p=none' means DMARC only monitors and reports — "
                    "spoofed mail that fails SPF is still delivered exactly "
                    "as if nothing were wrong."
                ),
                remediation=(
                    "Move the policy to 'p=quarantine' or 'p=reject' once "
                    "legitimate mail sources are confirmed to pass SPF."
                ),
                evidence_items=dmarc_evidence,
            )
        return Finding(
            id="dmarc-record",
            title=f"DMARC policy enforced (p={policy})",
            category="DNS",
            severity=Severity.INFO,
            status=Status.PASS,
            owasp=OWASP_MISCONFIG,
            evidence=dmarc,
            evidence_items=dmarc_evidence,
        )
