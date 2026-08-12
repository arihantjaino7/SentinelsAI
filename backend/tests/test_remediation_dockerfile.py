"""Tests for remediation/dockerfile.py -- the non-root USER fixer."""
from __future__ import annotations

import base64
import json

from models import Finding, Severity, Status
from remediation.dockerfile import DockerRootUserFixer, _detect_family
from remediation.source import FileSource


def _contents_response(sha: str, content: str) -> tuple[int, dict, str]:
    body = json.dumps({
        "sha": sha,
        "encoding": "base64",
        "content": base64.b64encode(content.encode()).decode(),
    })
    return (200, {"content-type": "application/json"}, body)


def _finding(**overrides) -> Finding:
    defaults = dict(
        id="docker-root-user-Dockerfile",
        title="Dockerfile never switches away from root",
        category="Configuration",
        severity=Severity.MEDIUM,
        status=Status.WARN,
        file_path="Dockerfile",
        line=1,
    )
    defaults.update(overrides)
    return Finding(**defaults)


# --- _detect_family: pure, offline ------------------------------------------


def test_detect_family_alpine():
    assert _detect_family("FROM python:3.12-alpine\n") == "alpine"


def test_detect_family_defaults_to_debian():
    assert _detect_family("FROM python:3.12-slim\n") == "debian"


def test_detect_family_uses_last_from_in_multistage_build():
    text = "FROM node:20 AS build\nRUN npm ci\nFROM python:3.12-alpine\nCOPY --from=build /app /app\n"
    assert _detect_family(text) == "alpine"


# --- DockerRootUserFixer.handles --------------------------------------------


def test_handles_only_docker_root_user_ids():
    fixer = DockerRootUserFixer()
    assert fixer.handles(_finding())
    assert not fixer.handles(_finding(id="docker-latest-tag-Dockerfile-L1"))


# --- DockerRootUserFixer.plan -----------------------------------------------


async def test_plan_inserts_user_before_last_cmd(mock_site):
    dockerfile = "FROM python:3.12-slim\nCOPY . /app\nCMD [\"python\", \"app.py\"]\n"
    routes = {"/repos/octo/demo/contents/Dockerfile": _contents_response("sha1", dockerfile)}
    client = mock_site(routes, base_url="https://api.github.com")
    files = FileSource(client=client, owner="octo", repo="demo", ref="main")
    plan = await DockerRootUserFixer().plan(_finding(), files)
    await client.aclose()

    assert plan is not None
    assert plan.tier == 2
    patch = plan.patches[0]
    assert patch.path == "Dockerfile"
    assert patch.action == "modify"
    lines = patch.new_content.splitlines()
    cmd_index = next(i for i, l in enumerate(lines) if l.startswith("CMD"))
    user_index = next(i for i, l in enumerate(lines) if l.startswith("USER"))
    assert user_index < cmd_index


async def test_plan_appends_user_when_no_cmd_or_entrypoint(mock_site):
    dockerfile = "FROM python:3.12-slim\nCOPY . /app\n"
    routes = {"/repos/octo/demo/contents/Dockerfile": _contents_response("sha1", dockerfile)}
    client = mock_site(routes, base_url="https://api.github.com")
    files = FileSource(client=client, owner="octo", repo="demo", ref="main")
    plan = await DockerRootUserFixer().plan(_finding(), files)
    await client.aclose()
    assert plan is not None
    assert "USER" in plan.patches[0].new_content


async def test_plan_returns_none_when_user_already_present(mock_site):
    dockerfile = "FROM python:3.12-slim\nUSER appuser\nCMD [\"python\", \"app.py\"]\n"
    routes = {"/repos/octo/demo/contents/Dockerfile": _contents_response("sha1", dockerfile)}
    client = mock_site(routes, base_url="https://api.github.com")
    files = FileSource(client=client, owner="octo", repo="demo", ref="main")
    plan = await DockerRootUserFixer().plan(_finding(), files)
    await client.aclose()
    assert plan is None


async def test_plan_returns_none_when_file_is_gone(mock_site):
    routes: dict = {}
    client = mock_site(routes, base_url="https://api.github.com")
    files = FileSource(client=client, owner="octo", repo="demo", ref="main")
    plan = await DockerRootUserFixer().plan(_finding(), files)
    await client.aclose()
    assert plan is None
