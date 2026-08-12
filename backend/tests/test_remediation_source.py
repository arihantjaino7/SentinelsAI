"""Tests for remediation/source.py -- the GitHub Contents API fetch layer.
All against a mocked transport (this suite's `mock_site` fixture); no real
GitHub call, matching conftest.py's rule for the whole test suite.
"""
from __future__ import annotations

import base64
import json

from remediation.source import FileSource, get_file, resolve_default_ref, resolve_ref_sha


def _contents_response(sha: str, content: str) -> tuple[int, dict, str]:
    body = json.dumps({
        "sha": sha,
        "encoding": "base64",
        "content": base64.b64encode(content.encode()).decode(),
    })
    return (200, {"content-type": "application/json"}, body)


async def test_get_file_decodes_base64_content(mock_site):
    routes = {"/repos/octo/demo/contents/README.md": _contents_response("abc123", "hello world")}
    client = mock_site(routes, base_url="https://api.github.com")
    result = await get_file(client, "octo", "demo", "README.md", "main")
    await client.aclose()
    assert result is not None
    assert result.content == "hello world"
    assert result.sha == "abc123"


async def test_get_file_returns_none_on_404(mock_site):
    client = mock_site({}, base_url="https://api.github.com")
    result = await get_file(client, "octo", "demo", "missing.txt", "main")
    await client.aclose()
    assert result is None


async def test_get_file_returns_none_for_a_directory(mock_site):
    routes = {"/repos/octo/demo/contents/src": (200, {"content-type": "application/json"}, json.dumps([{"name": "a.py"}]))}
    client = mock_site(routes, base_url="https://api.github.com")
    result = await get_file(client, "octo", "demo", "src", "main")
    await client.aclose()
    assert result is None


async def test_resolve_default_ref_reads_default_branch(mock_site):
    routes = {"/repos/octo/demo": (200, {"content-type": "application/json"}, json.dumps({"default_branch": "trunk"}))}
    client = mock_site(routes, base_url="https://api.github.com")
    ref = await resolve_default_ref(client, "octo", "demo")
    await client.aclose()
    assert ref == "trunk"


async def test_resolve_ref_sha_returns_full_sha(mock_site):
    routes = {"/repos/foo/bar/commits/v2": (200, {"content-type": "application/json"}, json.dumps({"sha": "deadbeef" * 5}))}
    client = mock_site(routes, base_url="https://api.github.com")
    sha = await resolve_ref_sha(client, "foo", "bar", "v2")
    await client.aclose()
    assert sha == "deadbeef" * 5


async def test_resolve_ref_sha_returns_none_on_404(mock_site):
    client = mock_site({}, base_url="https://api.github.com")
    sha = await resolve_ref_sha(client, "foo", "bar", "nope")
    await client.aclose()
    assert sha is None


async def test_file_source_get_delegates_with_bound_repo_and_ref(mock_site):
    routes = {"/repos/octo/demo/contents/a.txt": _contents_response("sha", "content")}
    client = mock_site(routes, base_url="https://api.github.com")
    files = FileSource(client=client, owner="octo", repo="demo", ref="main")
    result = await files.get("a.txt")
    await client.aclose()
    assert result is not None
    assert result.path == "a.txt"
