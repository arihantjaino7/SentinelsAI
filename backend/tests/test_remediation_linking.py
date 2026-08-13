"""Tests for remediation/linking.py -- repo_target() (PLAN-v5 Stage D)."""
from __future__ import annotations

import pytest

from models import ScanReport
from remediation.linking import NoRepoTarget, repo_target
from storage.scan_links import save_scan_repo_link
from storage.scans import save_scan
from storage.users import sign_in

SCAN_ID = "a1b2c3d4-0000-4000-8000-000000000077"


def _user():
    return sign_in(
        github_id=1, github_login="octo", avatar_url=None,
        token_hash="hash1", expires_at="2099-01-01T00:00:00+00:00",
    )


def test_repo_scan_parses_its_own_url():
    report = ScanReport(
        id=SCAN_ID, url="https://github.com/octo/demo", target_type="repo",
        scanned_at="2026-08-13T00:00:00+00:00", duration_ms=1, score=80, grade="B",
    )
    assert repo_target(report) == ("octo", "demo", None)


def test_repo_scan_with_a_ref_carries_it_through():
    report = ScanReport(
        id=SCAN_ID, url="https://github.com/octo/demo/tree/dev", target_type="repo",
        scanned_at="2026-08-13T00:00:00+00:00", duration_ms=1, score=80, grade="B",
    )
    assert repo_target(report) == ("octo", "demo", "dev")


def test_url_scan_with_no_link_raises(temp_db):
    report = ScanReport(
        id=SCAN_ID, url="https://example.com", target_type="url",
        scanned_at="2026-08-13T00:00:00+00:00", duration_ms=1, score=60, grade="D",
    )
    with pytest.raises(NoRepoTarget, match="linked repository"):
        repo_target(report)


def test_url_scan_with_a_link_reads_it(temp_db):
    user = _user()
    report = ScanReport(
        id=SCAN_ID, url="https://example.com", target_type="url",
        scanned_at="2026-08-13T00:00:00+00:00", duration_ms=1, score=60, grade="D",
    )
    save_scan(report, user_id=user.id)
    save_scan_repo_link(SCAN_ID, user.id, 500, "octo", "demo", ref="staging")
    assert repo_target(report) == ("octo", "demo", "staging")
