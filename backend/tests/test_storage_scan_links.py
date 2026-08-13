"""Tests for storage/scan_links.py -- the scan_repo_links table (PLAN-v5
Stage D)."""
from __future__ import annotations

from models import ScanReport
from storage.scan_links import delete_scan_repo_link, get_scan_repo_link, save_scan_repo_link
from storage.scans import save_scan
from storage.users import sign_in

SCAN_ID = "a1b2c3d4-0000-4000-8000-000000000099"


def _user(github_id: int = 1, login: str = "octo"):
    return sign_in(
        github_id=github_id, github_login=login, avatar_url=None,
        token_hash=f"hash{github_id}", expires_at="2099-01-01T00:00:00+00:00",
    )


def _seed_scan(user_id: int) -> ScanReport:
    report = ScanReport(
        id=SCAN_ID, url="https://example.com", target_type="url",
        scanned_at="2026-08-13T00:00:00+00:00", duration_ms=10, score=60, grade="D",
    )
    save_scan(report, user_id=user_id)
    return report


def test_get_returns_none_when_unlinked(temp_db):
    user = _user()
    _seed_scan(user.id)
    assert get_scan_repo_link(SCAN_ID) is None


def test_save_and_get_a_link(temp_db):
    user = _user()
    _seed_scan(user.id)
    link = save_scan_repo_link(SCAN_ID, user.id, 500, "octo", "demo", ref="main")
    assert link.owner == "octo"
    assert link.repo == "demo"
    assert link.ref == "main"

    found = get_scan_repo_link(SCAN_ID)
    assert found is not None
    assert found.repo == "demo"


def test_relinking_replaces_the_row_rather_than_adding_a_second_one(temp_db):
    user = _user()
    _seed_scan(user.id)
    save_scan_repo_link(SCAN_ID, user.id, 500, "octo", "demo")
    save_scan_repo_link(SCAN_ID, user.id, 501, "octo", "other-repo")
    found = get_scan_repo_link(SCAN_ID)
    assert found.repo == "other-repo"
    assert found.installation_id == 501


def test_delete_scoped_to_the_owner(temp_db):
    owner = _user(1, "octo")
    other = _user(2, "mallory")
    _seed_scan(owner.id)
    save_scan_repo_link(SCAN_ID, owner.id, 500, "octo", "demo")

    assert delete_scan_repo_link(SCAN_ID, other.id) is False
    assert get_scan_repo_link(SCAN_ID) is not None

    assert delete_scan_repo_link(SCAN_ID, owner.id) is True
    assert get_scan_repo_link(SCAN_ID) is None
