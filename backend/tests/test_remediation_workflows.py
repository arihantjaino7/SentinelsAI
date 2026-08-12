"""Tests for remediation/workflows.py -- the GitHub Actions pinning fixer.

`rewrite_uses_line` is tested with no network at all (PLAN-v5.md conflict #3:
"a pure line-rewrite function, offline-testable"). `WorkflowPinFixer.plan`
is tested against a mocked transport (this suite's `mock_site` fixture),
never a real GitHub call.
"""
from __future__ import annotations

import base64
import json

from models import Finding, Severity, Status
from remediation.source import FileSource
from remediation.workflows import WorkflowPinFixer, rewrite_uses_line

FULL_SHA = "a" * 40


def _finding(**overrides) -> Finding:
    defaults = dict(
        id="ci-unpinned-action-github-workflows-ci-yml-L2",
        title="Third-party action not pinned",
        category="Configuration",
        severity=Severity.MEDIUM,
        status=Status.WARN,
        file_path=".github/workflows/ci.yml",
        line=2,
    )
    defaults.update(overrides)
    return Finding(**defaults)


def _contents_response(sha: str, content: str) -> tuple[int, dict, str]:
    body = json.dumps({
        "sha": sha,
        "encoding": "base64",
        "content": base64.b64encode(content.encode()).decode(),
    })
    return (200, {"content-type": "application/json"}, body)


def _commit_response(sha: str) -> tuple[int, dict, str]:
    return (200, {"content-type": "application/json"}, json.dumps({"sha": sha}))


# --- rewrite_uses_line: pure, offline -----------------------------------


def test_rewrite_uses_line_replaces_ref_with_sha():
    line = "      uses: foo/bar@v2\n"
    result = rewrite_uses_line(line, "v2", FULL_SHA)
    assert result == f"      uses: foo/bar@{FULL_SHA}  # v2\n"


def test_rewrite_uses_line_preserves_crlf_ending():
    line = "uses: foo/bar@v2\r\n"
    result = rewrite_uses_line(line, "v2", FULL_SHA)
    assert result.endswith("\r\n")


def test_rewrite_uses_line_replaces_existing_trailing_comment():
    line = "uses: foo/bar@v2 # old note\n"
    result = rewrite_uses_line(line, "v2", FULL_SHA)
    assert result == f"uses: foo/bar@{FULL_SHA}  # v2\n"
    assert "old note" not in result


def test_rewrite_uses_line_returns_none_when_ref_not_present():
    line = "uses: foo/bar@v3\n"
    assert rewrite_uses_line(line, "v2", FULL_SHA) is None


def test_rewrite_uses_line_returns_none_without_uses_keyword():
    assert rewrite_uses_line("  - run: echo v2\n", "v2", FULL_SHA) is None


# --- WorkflowPinFixer.handles ---------------------------------------------


def test_handles_only_ci_unpinned_action_ids():
    fixer = WorkflowPinFixer()
    assert fixer.handles(_finding())
    assert not fixer.handles(_finding(id="docker-root-user-Dockerfile"))


# --- WorkflowPinFixer.plan: mocked network --------------------------------


async def test_plan_pins_the_unpinned_action(mock_site):
    workflow_text = "name: CI\njobs:\n  build:\n    steps:\n      uses: foo/bar@v2\n"
    routes = {
        "/repos/octo/demo/contents/.github/workflows/ci.yml": _contents_response("blobsha", workflow_text),
        "/repos/foo/bar/commits/v2": _commit_response(FULL_SHA),
    }
    finding = _finding(line=5)
    client = mock_site(routes, base_url="https://api.github.com")
    files = FileSource(client=client, owner="octo", repo="demo", ref="main")
    plan = await WorkflowPinFixer().plan(finding, files)
    await client.aclose()

    assert plan is not None
    assert plan.tier == 1
    assert len(plan.patches) == 1
    patch = plan.patches[0]
    assert patch.path == ".github/workflows/ci.yml"
    assert patch.action == "modify"
    assert patch.original_sha == "blobsha"
    assert f"@{FULL_SHA}" in patch.new_content
    assert "# v2" in patch.new_content


async def test_plan_returns_none_when_already_pinned(mock_site):
    workflow_text = f"uses: foo/bar@{FULL_SHA}\n"
    routes = {
        "/repos/octo/demo/contents/.github/workflows/ci.yml": _contents_response("blobsha", workflow_text),
    }
    finding = _finding(line=1)
    client = mock_site(routes, base_url="https://api.github.com")
    files = FileSource(client=client, owner="octo", repo="demo", ref="main")
    plan = await WorkflowPinFixer().plan(finding, files)
    await client.aclose()
    assert plan is None


async def test_plan_returns_none_when_file_is_gone(mock_site):
    routes: dict = {}
    finding = _finding(line=1)
    client = mock_site(routes, base_url="https://api.github.com")
    files = FileSource(client=client, owner="octo", repo="demo", ref="main")
    plan = await WorkflowPinFixer().plan(finding, files)
    await client.aclose()
    assert plan is None


async def test_plan_returns_none_when_sha_resolution_fails(mock_site):
    workflow_text = "uses: foo/bar@v2\n"
    routes = {
        "/repos/octo/demo/contents/.github/workflows/ci.yml": _contents_response("blobsha", workflow_text),
        # no /repos/foo/bar/commits/v2 route -- resolves to a 404
    }
    finding = _finding(line=1)
    client = mock_site(routes, base_url="https://api.github.com")
    files = FileSource(client=client, owner="octo", repo="demo", ref="main")
    plan = await WorkflowPinFixer().plan(finding, files)
    await client.aclose()
    assert plan is None


async def test_plan_returns_none_without_file_path_or_line():
    files = FileSource(client=None, owner="o", repo="r", ref="main")  # type: ignore[arg-type]
    finding = _finding(file_path=None, line=None)
    plan = await WorkflowPinFixer().plan(finding, files)
    assert plan is None
