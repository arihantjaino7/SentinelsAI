"""Tests for remediation/gitignore.py -- creates-only .gitignore fixer."""
from __future__ import annotations

import json

from models import Finding, Severity, Status
from remediation.gitignore import GitignoreFixer
from remediation.source import FileSource


def _finding() -> Finding:
    return Finding(
        id="gitignore-present",
        title="No .gitignore file found",
        category="Configuration",
        severity=Severity.MEDIUM,
        status=Status.FAIL,
    )


def test_handles_only_gitignore_present():
    fixer = GitignoreFixer()
    assert fixer.handles(_finding())
    assert not fixer.handles(Finding(id="gitignore-env", title="t", category="c", severity=Severity.HIGH, status=Status.FAIL))


async def test_plan_creates_gitignore_when_missing(mock_site):
    routes: dict = {}  # every contents lookup 404s -- no .gitignore exists
    client = mock_site(routes, base_url="https://api.github.com")
    files = FileSource(client=client, owner="octo", repo="demo", ref="main")
    plan = await GitignoreFixer().plan(_finding(), files)
    await client.aclose()

    assert plan is not None
    assert plan.tier == 1
    assert len(plan.patches) == 1
    patch = plan.patches[0]
    assert patch.path == ".gitignore"
    assert patch.action == "create"
    assert patch.original_sha is None
    assert ".env" in patch.new_content


async def test_plan_returns_none_when_gitignore_already_exists(mock_site):
    body = json.dumps({"sha": "abc", "encoding": "base64", "content": ""})
    routes = {"/repos/octo/demo/contents/.gitignore": (200, {"content-type": "application/json"}, body)}
    client = mock_site(routes, base_url="https://api.github.com")
    files = FileSource(client=client, owner="octo", repo="demo", ref="main")
    plan = await GitignoreFixer().plan(_finding(), files)
    await client.aclose()
    assert plan is None
