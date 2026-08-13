"""Tests for remediation/headers_fix.py -- SecurityHeaderFixer (PLAN-v5 Stage
D). No network involved: every case builds a FileSource against
`mock_site`'s fake transport.
"""
from __future__ import annotations

import base64
import json

from models import Finding, Severity, Status
from remediation.headers_fix import SecurityHeaderFixer
from remediation.source import FileSource


def _contents_response(sha: str, content: str) -> tuple[int, dict, str]:
    body = json.dumps({
        "sha": sha,
        "encoding": "base64",
        "content": base64.b64encode(content.encode()).decode(),
    })
    return (200, {"content-type": "application/json"}, body)


def _finding(id_: str = "missing-hsts", **overrides) -> Finding:
    defaults = dict(
        id=id_, title="t", category="Headers", severity=Severity.HIGH, status=Status.FAIL,
        agent="headers",
    )
    defaults.update(overrides)
    return Finding(**defaults)


def _files(routes: dict, mock_site) -> FileSource:
    client = mock_site(routes, base_url="https://api.github.com")
    return FileSource(client=client, owner="octo", repo="demo", ref="main")


def test_handles_only_the_four_header_ids():
    fixer = SecurityHeaderFixer()
    assert fixer.handles(_finding("missing-hsts"))
    assert fixer.handles(_finding("missing-csp"))
    assert fixer.handles(_finding("missing-x-content-type-options"))
    assert fixer.handles(_finding("missing-x-frame-options"))
    assert not fixer.handles(_finding("spf-record"))


async def test_plan_returns_none_for_unrecognized_stack(mock_site):
    plan = await SecurityHeaderFixer().plan(_finding(), _files({}, mock_site))
    assert plan is None


# --- Vercel -------------------------------------------------------------------


async def test_vercel_adds_a_new_headers_entry(mock_site):
    routes = {"/repos/octo/demo/contents/vercel.json": _contents_response("v1", "{}")}
    plan = await SecurityHeaderFixer().plan(_finding("missing-hsts"), _files(routes, mock_site))
    assert plan is not None
    assert plan.tier == 2
    assert plan.fixer_slug == "security-headers"
    patch = plan.patches[0]
    assert patch.path == "vercel.json"
    assert patch.action == "modify"
    data = json.loads(patch.new_content)
    keys = {h["key"] for h in data["headers"][0]["headers"]}
    assert "Strict-Transport-Security" in keys


async def test_vercel_appends_to_an_existing_matching_entry(mock_site):
    existing = json.dumps({
        "headers": [{"source": "/(.*)", "headers": [{"key": "X-Frame-Options", "value": "DENY"}]}]
    })
    routes = {"/repos/octo/demo/contents/vercel.json": _contents_response("v1", existing)}
    plan = await SecurityHeaderFixer().plan(_finding("missing-hsts"), _files(routes, mock_site))
    assert plan is not None
    data = json.loads(plan.patches[0].new_content)
    assert len(data["headers"]) == 1  # merged into the existing entry, not a second one
    keys = {h["key"] for h in data["headers"][0]["headers"]}
    assert {"X-Frame-Options", "Strict-Transport-Security"} <= keys


async def test_vercel_returns_none_when_already_fully_covered(mock_site):
    existing = json.dumps({
        "headers": [{
            "source": "/(.*)",
            "headers": [
                {"key": "Content-Security-Policy", "value": "default-src 'self'"},
                {"key": "Strict-Transport-Security", "value": "max-age=31536000; includeSubDomains"},
                {"key": "X-Content-Type-Options", "value": "nosniff"},
                {"key": "X-Frame-Options", "value": "DENY"},
            ],
        }]
    })
    routes = {"/repos/octo/demo/contents/vercel.json": _contents_response("v1", existing)}
    plan = await SecurityHeaderFixer().plan(_finding("missing-hsts"), _files(routes, mock_site))
    assert plan is None


async def test_vercel_returns_none_for_malformed_json(mock_site):
    routes = {"/repos/octo/demo/contents/vercel.json": _contents_response("v1", "{not json")}
    plan = await SecurityHeaderFixer().plan(_finding("missing-hsts"), _files(routes, mock_site))
    assert plan is None


# --- Next.js --------------------------------------------------------------


async def test_next_creates_config_when_none_exists(mock_site):
    routes = {
        "/repos/octo/demo/contents/vercel.json": (404, {}, ""),
        "/repos/octo/demo/contents/next.config.ts": (404, {}, ""),
        "/repos/octo/demo/contents/next.config.js": (404, {}, ""),
        "/repos/octo/demo/contents/next.config.mjs": (404, {}, ""),
        "/repos/octo/demo/contents/package.json": _contents_response(
            "p1", '{"dependencies": {"next": "^14.0.0"}}'
        ),
    }
    plan = await SecurityHeaderFixer().plan(_finding("missing-csp"), _files(routes, mock_site))
    assert plan is not None
    patch = plan.patches[0]
    assert patch.action == "create"
    assert patch.path == "next.config.ts"
    assert "async headers()" in patch.new_content
    assert "Content-Security-Policy" in patch.new_content


async def test_next_inserts_headers_into_existing_config_with_none(mock_site):
    existing = 'import type { NextConfig } from "next";\n\nconst nextConfig: NextConfig = {\n  reactStrictMode: true,\n};\n\nexport default nextConfig;\n'
    routes = {"/repos/octo/demo/contents/next.config.ts": _contents_response("n1", existing)}
    plan = await SecurityHeaderFixer().plan(_finding("missing-csp"), _files(routes, mock_site))
    assert plan is not None
    patch = plan.patches[0]
    assert patch.action == "modify"
    assert "async headers()" in patch.new_content
    assert "reactStrictMode: true" in patch.new_content  # nothing else was touched


async def test_next_declines_when_headers_already_defined(mock_site):
    existing = "module.exports = {\n  async headers() { return []; },\n};\n"
    routes = {"/repos/octo/demo/contents/next.config.ts": _contents_response("n1", existing)}
    plan = await SecurityHeaderFixer().plan(_finding("missing-csp"), _files(routes, mock_site))
    assert plan is None


async def test_next_declines_when_no_export_anchor_found(mock_site):
    existing = "// just a comment, no exported object literal\n"
    routes = {"/repos/octo/demo/contents/next.config.ts": _contents_response("n1", existing)}
    plan = await SecurityHeaderFixer().plan(_finding("missing-csp"), _files(routes, mock_site))
    assert plan is None
