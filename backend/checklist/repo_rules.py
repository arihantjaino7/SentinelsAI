"""Declarative checklist rules for repo scans -- the repo-side sibling of
`checklist/rules.py`. Same three-tier shape (auto/inferred/self_attested).

One real difference from the URL rules: most URL findings have exactly one
fixed `Finding.id` per check ("missing-csp" is always "missing-csp"), so
`_from_finding` can just look that id up. Several repo agents (secrets,
dependencies, the Dockerfile/CI/code-pattern checks) instead emit one finding
*per occurrence* -- a repo with three leaked keys produces three different
`Finding.id`s, one per key. Rules that cover those checks match by category
or id-prefix across the whole finding list instead (`_any`, below).

`_find`/`_from_finding` are copied rather than imported from `checklist.rules`
-- same small-duplication-over-coupling instinct `agents/repo/base.py`
documents for `BaseRepoAgent` vs `BaseAgent`.
"""
from __future__ import annotations

from models import Finding, Status
from checklist.rules import ChecklistRule


def _find(findings: list[Finding], id_: str) -> Finding | None:
    return next((f for f in findings if f.id == id_), None)


def _from_finding(
    findings: list[Finding],
    id_: str,
    *,
    absent_state: str = "pass",
    absent_explanation: str = "Check passed.",
) -> tuple[str, str, str]:
    f = _find(findings, id_)
    if f is None:
        return absent_state, absent_explanation, ""
    if f.status == Status.FAIL:
        return "fail", f.description or f.title, f.remediation or ""
    if f.status == Status.WARN:
        return "warn", f.description or f.title, f.remediation or ""
    return "pass", f.title, ""


def _any(
    findings: list[Finding],
    *,
    category: str | None = None,
    id_prefix: str | None = None,
    statuses: tuple[Status, ...] = (Status.FAIL,),
) -> list[Finding]:
    """Every finding matching category and/or id-prefix, restricted to statuses."""
    return [
        f for f in findings
        if f.status in statuses
        and (category is None or f.category == category)
        and (id_prefix is None or f.id.startswith(id_prefix))
    ]


# ── named helpers for rules that need slightly special logic ──────────────────

def _eval_no_secrets(findings: list[Finding]) -> tuple[str, str, str]:
    hits = _any(findings, category="Secrets")
    if not hits:
        return "pass", "No committed secrets were found.", ""
    plural = "s" if len(hits) != 1 else ""
    return (
        "fail",
        f"{len(hits)} possible secret{plural} committed to the repository -- "
        "see the Secrets agent for file/line detail.",
        "Remove every committed secret, rotate each credential immediately "
        "(it remains in git history even after deletion), and load secrets "
        "from environment variables or a secret manager instead.",
    )


def _eval_env_gitignored(findings: list[Finding]) -> tuple[str, str, str]:
    # No .gitignore at all -- .env definitely isn't covered by anything.
    missing = _find(findings, "gitignore-present")
    if missing is not None and missing.status == Status.FAIL:
        return (
            "fail",
            "This repository has no .gitignore file at all, so nothing "
            "stops a .env file from being committed.",
            "Add a .gitignore that covers .env, .env.local, and other "
            "secret-holding files.",
        )
    return _from_finding(findings, "gitignore-env")


def _eval_private_keys_gitignored(findings: list[Finding]) -> tuple[str, str, str]:
    missing = _find(findings, "gitignore-present")
    if missing is not None and missing.status == Status.FAIL:
        return (
            "fail",
            "This repository has no .gitignore file at all, so nothing "
            "stops a private key file from being committed.",
            "Add a .gitignore that covers *.pem, *.key, and other private-key files.",
        )
    return _from_finding(findings, "gitignore-private-keys")


def _eval_no_vulnerable_deps(findings: list[Finding]) -> tuple[str, str, str]:
    hits = _any(findings, category="Dependencies")
    if hits:
        word = "dependency" if len(hits) == 1 else "dependencies"
        return (
            "fail",
            f"{len(hits)} {word} with known vulnerabilities in the OSV.dev "
            "database -- see the Dependencies agent for detail.",
            "Upgrade each flagged dependency past its vulnerable version, then re-scan.",
        )
    unverified = _find(findings, "dependency-osv-unreachable")
    if unverified is not None:
        return "warn", unverified.description or unverified.title, ""
    return "pass", "No known-vulnerable dependencies found.", ""


def _eval_code_patterns(findings: list[Finding]) -> tuple[str, str, str]:
    hits = _any(findings, category="Code Patterns", statuses=(Status.WARN, Status.FAIL))
    if not hits:
        return "pass", "No risky code patterns detected.", ""
    return (
        "warn",
        f"{len(hits)} risky-looking code construct(s) found (eval, shell=True, "
        "string-built SQL, ...) -- indicative, not conclusive; see the Code "
        "Patterns agent for detail.",
        "Review each flagged line and replace it with the safer alternative noted there.",
    )


def _eval_dockerfile_hardened(findings: list[Finding]) -> tuple[str, str, str]:
    hits = _any(findings, id_prefix="docker-", statuses=(Status.WARN, Status.FAIL))
    if not hits:
        return "pass", "No Dockerfile hardening issues found (or no Dockerfile present).", ""
    return (
        "warn",
        f"{len(hits)} Dockerfile issue(s) found (root user, :latest tag, or a "
        "secret-shaped ENV/ARG) -- see the Repo Config agent for detail.",
        "Add a non-root USER, pin the base image tag, and move any secrets out of ENV/ARG.",
    )


def _eval_ci_workflow_safe(findings: list[Finding]) -> tuple[str, str, str]:
    hits = _any(findings, id_prefix="ci-", statuses=(Status.WARN, Status.FAIL))
    if not hits:
        return "pass", "No risky CI workflow settings found (or no workflow present).", ""
    return (
        "warn",
        f"{len(hits)} CI workflow risk(s) found (pull_request_target, an "
        "unpinned third-party action) -- see the Repo Config agent for detail.",
        "Avoid pull_request_target with untrusted checkouts, and pin third-party actions to a commit SHA.",
    )


def _eval_no_large_files(findings: list[Finding]) -> tuple[str, str, str]:
    hits = _any(findings, id_prefix="repo-large-file-", statuses=(Status.WARN,))
    if not hits:
        return "pass", "No unusually large files found.", ""
    return (
        "warn",
        f"{len(hits)} large file(s) committed -- see the Repo Hygiene agent for detail.",
        "Move large assets/data out of the repo (e.g. Git LFS or external storage).",
    )


REPO_RULES: list[ChecklistRule] = [
    # ── Auto-verified, blocking ─────────────────────────────────────────────
    ChecklistRule(
        key="repo_no_secrets_committed",
        title="No secrets committed",
        tier="auto",
        agent="repo-secrets",
        blocking=True,
        evaluate=_eval_no_secrets,
    ),
    ChecklistRule(
        key="repo_env_gitignored",
        title=".env is gitignored",
        tier="auto",
        agent="repo-config",
        blocking=True,
        evaluate=_eval_env_gitignored,
    ),
    ChecklistRule(
        key="repo_no_vulnerable_dependencies",
        title="No known-vulnerable dependencies",
        tier="auto",
        agent="repo-dependencies",
        blocking=True,
        evaluate=_eval_no_vulnerable_deps,
    ),
    # ── Auto-verified, non-blocking ─────────────────────────────────────────
    ChecklistRule(
        key="repo_private_keys_gitignored",
        title="Private key files are gitignored",
        tier="auto",
        agent="repo-config",
        evaluate=_eval_private_keys_gitignored,
    ),
    ChecklistRule(
        key="repo_readme_present",
        title="README present",
        tier="auto",
        agent="repo-hygiene",
        evaluate=lambda f: _from_finding(f, "repo-readme-present"),
    ),
    ChecklistRule(
        key="repo_license_present",
        title="LICENSE present",
        tier="auto",
        agent="repo-hygiene",
        evaluate=lambda f: _from_finding(f, "repo-license-present"),
    ),
    ChecklistRule(
        key="repo_env_example_present",
        title=".env example/template provided",
        tier="auto",
        agent="repo-hygiene",
        evaluate=lambda f: _from_finding(f, "repo-env-example-present"),
    ),
    ChecklistRule(
        key="repo_ci_configured",
        title="CI is configured",
        tier="auto",
        agent="repo-hygiene",
        evaluate=lambda f: _from_finding(f, "repo-ci-configured"),
    ),
    ChecklistRule(
        key="repo_tests_present",
        title="Test files present",
        tier="auto",
        agent="repo-hygiene",
        evaluate=lambda f: _from_finding(f, "repo-tests-present"),
    ),
    # ── Passively inferred ───────────────────────────────────────────────────
    ChecklistRule(
        key="repo_no_risky_code_patterns",
        title="No risky code patterns detected",
        tier="inferred",
        agent="repo-patterns",
        evaluate=_eval_code_patterns,
    ),
    ChecklistRule(
        key="repo_dockerfile_hardened",
        title="Dockerfile follows basic hardening practice",
        tier="inferred",
        agent="repo-config",
        evaluate=_eval_dockerfile_hardened,
    ),
    ChecklistRule(
        key="repo_ci_workflow_safe",
        title="CI workflow avoids common supply-chain risks",
        tier="inferred",
        agent="repo-config",
        evaluate=_eval_ci_workflow_safe,
    ),
    ChecklistRule(
        key="repo_no_large_files",
        title="No unusually large files committed",
        tier="inferred",
        agent="repo-hygiene",
        evaluate=_eval_no_large_files,
    ),
    # ── Self-attested ─────────────────────────────────────────────────────────
    ChecklistRule(
        key="repo_secrets_rotated",
        title="Any previously-committed secrets have been rotated",
        tier="self_attested",
        agent=None,
        evaluate=lambda _: (
            "unknown",
            "Sentinels cannot test this passively. If the Secrets agent ever "
            "flagged a credential in this repo's history, confirm it has "
            "been rotated -- deleting the line does not invalidate it.",
            "Rotate every credential that was ever committed, even after removing it from the current code.",
        ),
    ),
    ChecklistRule(
        key="repo_branch_protection",
        title="Branch protection enabled on the default branch",
        tier="self_attested",
        agent=None,
        evaluate=lambda _: (
            "unknown",
            "Sentinels cannot test this passively -- branch protection is a "
            "repository setting, not something visible in the tarball. "
            "Confirm the default branch requires review and blocks force-pushes.",
            "Enable branch protection: require pull request review and status checks before merging.",
        ),
    ),
    ChecklistRule(
        key="repo_two_factor_auth",
        title="Two-factor authentication enforced for contributors",
        tier="self_attested",
        agent=None,
        evaluate=lambda _: (
            "unknown",
            "Sentinels cannot test this passively. Confirm 2FA is required "
            "for everyone with write access to this repository.",
            "Enable and enforce two-factor authentication for the organization or repository.",
        ),
    ),
    ChecklistRule(
        key="repo_code_review_required",
        title="Pull requests require review before merging",
        tier="self_attested",
        agent=None,
        evaluate=lambda _: (
            "unknown",
            "Sentinels cannot test this passively. Confirm at least one "
            "approving review is required before a pull request can merge.",
            "Require pull request review in the branch protection settings.",
        ),
    ),
]
