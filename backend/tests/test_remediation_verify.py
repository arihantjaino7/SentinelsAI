"""Tests for remediation/verify.py -- the half of the loop that checks whether
a fix actually worked (PLAN-v5 Stage C).

Nothing here touches the network: `fetch_repo` is replaced by a fake that
yields a directory built by the test, so "the repository after the merge" is
just a folder with files in it. The agent that runs over that folder is the
real `ConfigAgent`, and the score comes from the real `calculate_score` -- the
two things this stage must not fake, since the entire claim being tested is
"the numbers came from looking".
"""
from __future__ import annotations

import contextlib
from pathlib import Path

import pytest

from models import (
    AgentResult,
    FilePatch,
    Finding,
    FixApplicationState,
    FixPlan,
    ScanReport,
    Severity,
    Status,
)
from remediation import verify as verify_module
from remediation.tokens import InstallationToken, TokenProvider
from remediation.verify import VerifyError, verify_finding
from repo.fetch import RepoFetchResult
from storage.installations import save_installation
from storage.remediation import (
    list_audit,
    list_fix_applications,
    save_fix_application,
    save_fix_plan,
)
from storage.scans import get_scan, save_scan
from storage.users import sign_in

SCAN_ID = "a1b2c3d4-0000-4000-8000-000000000042"

# A .gitignore that covers .env and private keys -- what `gitignore.py`'s
# deterministic fixer creates, and therefore what the repository looks like
# after Sentinels' own pull request merges.
FIXED_GITIGNORE = ".env\n.env.local\n*.pem\n*.key\n"


class _FakeProvider(TokenProvider):
    async def token_for(self, client, installation_id):
        return InstallationToken(token="ghs_fake", expires_at="")


def _gitignore_finding() -> Finding:
    """The stored finding a repo with no .gitignore produces -- copied from
    what `ConfigAgent._check_gitignore` actually emits."""
    return Finding(
        id="gitignore-present",
        title="No .gitignore file found",
        category="Configuration",
        severity=Severity.MEDIUM,
        status=Status.FAIL,
        agent="repo-config",
    )


def _other_agents_finding() -> Finding:
    """A finding from a *different* agent. It must survive verification
    untouched: nothing re-observed it, so nothing may claim anything about it."""
    return Finding(
        id="repo-readme-present",
        title="No README",
        category="Repo Hygiene",
        severity=Severity.MEDIUM,
        status=Status.FAIL,
        agent="repo-hygiene",
    )


def _plan() -> FixPlan:
    return FixPlan(
        finding_key="gitignore-present",
        fixer_slug="gitignore-present",
        tier=1,
        summary="Add a .gitignore.",
        patches=[FilePatch(path=".gitignore", action="create", new_content=FIXED_GITIGNORE)],
        created_at="2026-08-12T00:00:00+00:00",
    )


def _seed(findings=None, owned=True, url="https://github.com/octo/demo",
          target_type="repo"):
    user = sign_in(
        github_id=1, github_login="octo", avatar_url=None,
        token_hash="hash1", expires_at="2099-01-01T00:00:00+00:00",
    )
    findings = findings if findings is not None else [
        _gitignore_finding(), _other_agents_finding()
    ]
    # `save_scan` persists findings underneath their agent runs, so a seeded
    # report needs those to be readable back -- which is what the
    # immutability test below actually checks.
    by_agent: dict[str, list[Finding]] = {}
    for finding in findings:
        by_agent.setdefault(finding.agent, []).append(finding)
    report = ScanReport(
        id=SCAN_ID,
        url=url,
        target_type=target_type,
        scanned_at="2026-08-12T00:00:00+00:00",
        duration_ms=100,
        score=84,
        grade="B",
        findings=findings,
        agents=[
            AgentResult(agent=agent, findings=agent_findings, duration_ms=10)
            for agent, agent_findings in by_agent.items()
        ],
    )
    save_scan(report, user_id=user.id if owned else None)
    save_fix_plan(report.id, _plan())
    return user, report


def _merged_application(scan_id: str = SCAN_ID, finding_key: str = "gitignore-present",
                        state: FixApplicationState = FixApplicationState.MERGED):
    plan = _plan()
    plan.finding_key = finding_key
    return save_fix_application(
        scan_id, plan, state, branch="sentinels/fix-a1b2c3d4-1786538197",
        pr_url="https://github.com/octo/demo/pull/1", pr_number=1,
    )


def _fake_repo(monkeypatch, root: Path, gitignore: str | None = FIXED_GITIGNORE) -> list[dict]:
    """Replace `fetch_repo` with a fake that yields `root`, optionally
    containing a .gitignore. Returns a log of what each call saw, so a test
    can assert on the headers the re-fetch went out with."""
    if gitignore is not None:
        (root / ".gitignore").write_text(gitignore, encoding="utf-8")
    (root / "app.py").write_text("print('hi')\n", encoding="utf-8")

    seen: list[dict] = []

    @contextlib.asynccontextmanager
    async def fake_fetch_repo(owner, repo, ref, client):
        seen.append({
            "owner": owner, "repo": repo, "ref": ref,
            "authorization": client.headers.get("authorization"),
        })
        yield RepoFetchResult(
            root=root, owner=owner, repo=repo, ref=ref or "main", default_branch="main"
        )

    monkeypatch.setattr(verify_module, "fetch_repo", fake_fetch_repo)
    return seen


# --- the happy path --------------------------------------------------------

async def test_a_merged_fix_that_worked_reports_a_real_positive_delta(
    temp_db, monkeypatch, tmp_path
):
    """Two medium findings (8 points each) -> 84. The .gitignore one is gone
    on the re-read, so the score is 92 and the delta is +8 -- computed by the
    untouched scorer, not by this module."""
    user, report = _seed()
    application = _merged_application()
    _fake_repo(monkeypatch, tmp_path)

    result = await verify_finding(report, user, "gitignore-present")

    assert result.before == 84
    assert result.after == 92
    assert result.delta == 8
    assert result.target_fixed is True
    assert result.fixed == ["gitignore-present"]
    assert result.still_failing == []
    assert result.agent == "repo-config"
    assert result.application_id == application.id
    assert result.recorded is True


async def test_the_application_row_moves_to_verified_and_keeps_the_evidence(
    temp_db, monkeypatch, tmp_path
):
    user, report = _seed()
    _merged_application()
    _fake_repo(monkeypatch, tmp_path)

    await verify_finding(report, user, "gitignore-present")

    stored = list_fix_applications(SCAN_ID)[0]
    assert stored.state == FixApplicationState.VERIFIED
    assert stored.verification is not None
    assert stored.verification.delta == 8
    assert stored.verification.target_fixed is True
    # The plan snapshot from Stage B is untouched by verification.
    assert stored.plan is not None and stored.plan.patches[0].path == ".gitignore"


async def test_the_verification_is_audited(temp_db, monkeypatch, tmp_path):
    user, report = _seed()
    _merged_application()
    _fake_repo(monkeypatch, tmp_path)

    await verify_finding(report, user, "gitignore-present")

    actions = [row["action"] for row in list_audit(SCAN_ID)]
    assert "fix_verified" in actions


async def test_the_original_scan_is_never_modified(temp_db, monkeypatch, tmp_path):
    """Scans are immutable history (PLAN-v5.md conflict #6): verification
    reads the stored report and writes only to the audit trail."""
    user, report = _seed()
    _merged_application()
    _fake_repo(monkeypatch, tmp_path)

    await verify_finding(report, user, "gitignore-present")

    stored = get_scan(SCAN_ID)
    assert stored is not None
    assert stored.score == 84
    assert sorted(f.id for f in stored.findings) == ["gitignore-present", "repo-readme-present"]


# --- the unhappy path, reported honestly -----------------------------------

async def test_a_fix_that_did_not_work_says_so(temp_db, monkeypatch, tmp_path):
    """The repository still has no .gitignore, so the finding fires again.
    The row still becomes `verified` -- that state means "we looked", and
    `target_fixed` carries what we saw."""
    user, report = _seed()
    _merged_application()
    _fake_repo(monkeypatch, tmp_path, gitignore=None)

    result = await verify_finding(report, user, "gitignore-present")

    assert result.target_fixed is False
    assert result.delta == 0
    assert result.still_failing == ["gitignore-present"]
    assert result.fixed == []
    assert list_fix_applications(SCAN_ID)[0].state == FixApplicationState.VERIFIED


async def test_a_crashed_agent_refuses_instead_of_claiming_success(
    temp_db, monkeypatch, tmp_path
):
    """The dangerous failure mode: an agent that blows up returns zero
    findings, which would score as "every problem is gone"."""
    user, report = _seed()
    _merged_application()
    _fake_repo(monkeypatch, tmp_path)

    class _BrokenAgent:
        name = "repo-config"

        async def run(self, context):
            from models import AgentResult
            return AgentResult(agent="repo-config", findings=[], duration_ms=1,
                               error="RuntimeError: boom")

    monkeypatch.setattr(verify_module, "repo_agent_for", lambda name: _BrokenAgent)

    with pytest.raises(VerifyError, match="failed while re-checking") as exc:
        await verify_finding(report, user, "gitignore-present")
    assert exc.value.status == 502
    assert list_fix_applications(SCAN_ID)[0].state == FixApplicationState.MERGED


async def test_only_the_responsible_agents_findings_are_replaced(
    temp_db, monkeypatch, tmp_path
):
    """The other agent's finding was not re-observed, so it stays a finding
    and keeps costing its points."""
    user, report = _seed()
    _merged_application()
    _fake_repo(monkeypatch, tmp_path)

    result = await verify_finding(report, user, "gitignore-present")

    assert "repo-readme-present" not in result.fixed
    assert result.after == 92  # 100 - 8 for the README finding that still stands


# --- gating ----------------------------------------------------------------

async def test_an_open_pull_request_is_refused_until_it_merges(
    temp_db, monkeypatch, tmp_path
):
    user, report = _seed()
    _merged_application(state=FixApplicationState.PR_OPEN)
    _fake_repo(monkeypatch, tmp_path)

    with pytest.raises(VerifyError, match="not been merged") as exc:
        await verify_finding(report, user, "gitignore-present")
    assert exc.value.status == 409
    assert list_fix_applications(SCAN_ID)[0].state == FixApplicationState.PR_OPEN


async def test_a_finding_with_no_application_row_is_still_verifiable(
    temp_db, monkeypatch, tmp_path
):
    """Someone can fix a finding by hand. Verification still works; there is
    just no audit row of ours to close out."""
    user, report = _seed()
    _fake_repo(monkeypatch, tmp_path)

    result = await verify_finding(report, user, "gitignore-present")

    assert result.target_fixed is True
    assert result.application_id is None
    assert result.recorded is False
    actions = [row["action"] for row in list_audit(SCAN_ID)]
    assert actions == ["fix_verified_unrecorded"]


async def test_re_verifying_an_already_verified_fix_is_allowed(
    temp_db, monkeypatch, tmp_path
):
    user, report = _seed()
    _merged_application()
    _fake_repo(monkeypatch, tmp_path)

    await verify_finding(report, user, "gitignore-present")
    again = await verify_finding(report, user, "gitignore-present")

    assert again.recorded is True
    assert list_fix_applications(SCAN_ID)[0].state == FixApplicationState.VERIFIED


async def test_an_unowned_scan_cannot_be_verified(temp_db, monkeypatch, tmp_path):
    user, report = _seed(owned=False)
    _fake_repo(monkeypatch, tmp_path)

    with pytest.raises(VerifyError) as exc:
        await verify_finding(report, user, "gitignore-present")
    assert exc.value.status == 403


async def test_another_users_scan_cannot_be_verified(temp_db, monkeypatch, tmp_path):
    _, report = _seed()
    _fake_repo(monkeypatch, tmp_path)
    intruder = sign_in(
        github_id=2, github_login="mallory", avatar_url=None,
        token_hash="hash2", expires_at="2099-01-01T00:00:00+00:00",
    )

    with pytest.raises(VerifyError) as exc:
        await verify_finding(report, intruder, "gitignore-present")
    assert exc.value.status == 403


async def test_a_url_scan_has_nothing_to_re_read(temp_db, monkeypatch, tmp_path):
    user, report = _seed(url="https://example.com", target_type="url")
    _fake_repo(monkeypatch, tmp_path)

    with pytest.raises(VerifyError, match="URL scan") as exc:
        await verify_finding(report, user, "gitignore-present")
    assert exc.value.status == 400


async def test_a_url_agents_finding_is_refused(temp_db, monkeypatch, tmp_path):
    """A repo scan cannot produce one, but the refusal has to be specific
    rather than "unknown agent" -- bridging URL findings to a repo is Stage D."""
    finding = _gitignore_finding()
    finding.agent = "headers"
    user, report = _seed(findings=[finding])
    _fake_repo(monkeypatch, tmp_path)

    with pytest.raises(VerifyError, match="live URL") as exc:
        await verify_finding(report, user, "gitignore-present")
    assert exc.value.status == 400


async def test_an_agent_that_no_longer_exists_is_refused(temp_db, monkeypatch, tmp_path):
    finding = _gitignore_finding()
    finding.agent = "repo-ghost"
    user, report = _seed(findings=[finding])
    _fake_repo(monkeypatch, tmp_path)

    with pytest.raises(VerifyError, match="no longer") as exc:
        await verify_finding(report, user, "gitignore-present")
    assert exc.value.status == 409


async def test_a_finding_not_in_the_scan_is_refused(temp_db, monkeypatch, tmp_path):
    user, report = _seed()
    _fake_repo(monkeypatch, tmp_path)

    with pytest.raises(VerifyError) as exc:
        await verify_finding(report, user, "not-a-finding")
    assert exc.value.status == 404


# --- reading the repository ------------------------------------------------

async def test_an_installation_token_authenticates_the_re_fetch(
    temp_db, monkeypatch, tmp_path
):
    """Verification re-downloads a tarball every run: unauthenticated, that
    is 60 requests an hour and no private repositories at all."""
    user, report = _seed()
    _merged_application()
    save_installation(user.id, 500, "octo", "selected")
    seen = _fake_repo(monkeypatch, tmp_path)

    await verify_finding(report, user, "gitignore-present", provider=_FakeProvider())

    assert seen[0]["authorization"] == "Bearer ghs_fake"
    assert (seen[0]["owner"], seen[0]["repo"]) == ("octo", "demo")


async def test_without_an_installation_the_read_is_unauthenticated(
    temp_db, monkeypatch, tmp_path
):
    """A public repository needs no grant, and verification writes nothing to
    GitHub -- so a missing installation is not a reason to refuse."""
    user, report = _seed()
    _merged_application()
    seen = _fake_repo(monkeypatch, tmp_path)

    result = await verify_finding(report, user, "gitignore-present")

    assert seen[0]["authorization"] is None
    assert result.target_fixed is True


async def test_a_repository_that_cannot_be_fetched_is_a_400(
    temp_db, monkeypatch, tmp_path
):
    user, report = _seed()
    _merged_application()

    @contextlib.asynccontextmanager
    async def exploding_fetch(owner, repo, ref, client):
        raise ValueError(f"GitHub repo {owner}/{repo} not found")
        yield  # pragma: no cover - makes this a generator

    monkeypatch.setattr(verify_module, "fetch_repo", exploding_fetch)

    with pytest.raises(VerifyError, match="not found") as exc:
        await verify_finding(report, user, "gitignore-present")
    assert exc.value.status == 400
