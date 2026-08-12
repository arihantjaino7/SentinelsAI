"""Tests for remediation/scaffolding.py -- ReadmeFixer and EnvExampleFixer."""
from __future__ import annotations

import base64
import json

from models import Finding, Severity, Status
from remediation.scaffolding import EnvExampleFixer, ReadmeFixer, _extract_env_keys
from remediation.source import FileSource


def _contents_response(sha: str, content: str) -> tuple[int, dict, str]:
    body = json.dumps({
        "sha": sha,
        "encoding": "base64",
        "content": base64.b64encode(content.encode()).decode(),
    })
    return (200, {"content-type": "application/json"}, body)


def _readme_finding() -> Finding:
    return Finding(id="repo-readme-present", title="No README", category="Hygiene", severity=Severity.LOW, status=Status.WARN)


def _env_finding() -> Finding:
    return Finding(id="repo-env-example-present", title="No .env.example", category="Hygiene", severity=Severity.LOW, status=Status.WARN)


# --- _extract_env_keys: pure, offline --------------------------------------


def test_extract_env_keys_skips_blank_lines_and_comments():
    text = "\n# a comment\nFOO=bar\nBAZ=\nexport QUX=1\nnot a line\n"
    assert _extract_env_keys(text) == ["FOO", "BAZ", "QUX"]


def test_extract_env_keys_deduplicates_preserving_order():
    text = "A=1\nB=2\nA=3\n"
    assert _extract_env_keys(text) == ["A", "B"]


# --- ReadmeFixer -------------------------------------------------------------


def test_readme_handles_only_repo_readme_present():
    fixer = ReadmeFixer()
    assert fixer.handles(_readme_finding())
    assert not fixer.handles(_env_finding())


async def test_readme_plan_creates_when_no_readme_variant_exists(mock_site):
    routes: dict = {}  # every candidate name 404s
    client = mock_site(routes, base_url="https://api.github.com")
    files = FileSource(client=client, owner="octo", repo="demo", ref="main")
    plan = await ReadmeFixer().plan(_readme_finding(), files)
    await client.aclose()

    assert plan is not None
    assert plan.patches[0].path == "README.md"
    assert plan.patches[0].action == "create"
    assert "demo" in plan.patches[0].new_content


async def test_readme_plan_returns_none_when_a_variant_already_exists(mock_site):
    routes = {"/repos/octo/demo/contents/readme.md": _contents_response("s", "hi")}
    client = mock_site(routes, base_url="https://api.github.com")
    files = FileSource(client=client, owner="octo", repo="demo", ref="main")
    plan = await ReadmeFixer().plan(_readme_finding(), files)
    await client.aclose()
    assert plan is None


# --- EnvExampleFixer ----------------------------------------------------------


def test_env_example_handles_only_repo_env_example_present():
    fixer = EnvExampleFixer()
    assert fixer.handles(_env_finding())
    assert not fixer.handles(_readme_finding())


async def test_env_example_plan_creates_from_committed_env_file(mock_site):
    routes = {
        "/repos/octo/demo/contents/.env": _contents_response("s", "API_KEY=secret123\nDEBUG=true\n"),
    }
    client = mock_site(routes, base_url="https://api.github.com")
    files = FileSource(client=client, owner="octo", repo="demo", ref="main")
    plan = await EnvExampleFixer().plan(_env_finding(), files)
    await client.aclose()

    assert plan is not None
    patch = plan.patches[0]
    assert patch.path == ".env.example"
    assert patch.action == "create"
    assert patch.new_content == "API_KEY=\nDEBUG=\n"
    assert "secret123" not in patch.new_content


async def test_env_example_plan_returns_none_when_no_env_file_exists(mock_site):
    routes: dict = {}
    client = mock_site(routes, base_url="https://api.github.com")
    files = FileSource(client=client, owner="octo", repo="demo", ref="main")
    plan = await EnvExampleFixer().plan(_env_finding(), files)
    await client.aclose()
    assert plan is None
