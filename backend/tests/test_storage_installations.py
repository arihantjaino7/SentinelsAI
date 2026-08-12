"""Tests for storage/installations.py -- which user granted Sentinels write
access to which GitHub account, and the lookup every write depends on.
"""
from __future__ import annotations

from storage.installations import (
    active_installation_for,
    list_installations,
    revoke_installation,
    save_installation,
)
from storage.users import sign_in


def _user(github_id: int = 1, login: str = "octo"):
    return sign_in(
        github_id=github_id,
        github_login=login,
        avatar_url=None,
        token_hash=f"hash{github_id}",
        expires_at="2099-01-01T00:00:00+00:00",
    )


def test_save_and_look_up_an_installation(temp_db):
    user = _user()
    save_installation(user.id, 500, "octo", "selected")
    found = active_installation_for(user.id, "octo")
    assert found is not None
    assert found.installation_id == 500
    assert found.repo_selection == "selected"


def test_account_matching_is_case_insensitive(temp_db):
    """GitHub account names are case-insensitive, so a scan of
    github.com/OctoCat/demo has to find the installation linked as `octocat`."""
    user = _user()
    save_installation(user.id, 500, "OctoCat", "all")
    assert active_installation_for(user.id, "octocat") is not None
    assert active_installation_for(user.id, "OCTOCAT") is not None


def test_re_saving_the_same_installation_updates_rather_than_duplicates(temp_db):
    user = _user()
    save_installation(user.id, 500, "octo", "selected")
    save_installation(user.id, 500, "octo", "all")
    installations = list_installations(user.id)
    assert len(installations) == 1
    assert installations[0].repo_selection == "all"


def test_another_users_installation_is_invisible(temp_db):
    owner = _user(1, "octo")
    other = _user(2, "someone-else")
    save_installation(owner.id, 500, "octo", "all")
    assert active_installation_for(other.id, "octo") is None


def test_revoked_installations_stop_being_found(temp_db):
    user = _user()
    save_installation(user.id, 500, "octo", "all")
    assert revoke_installation(user.id, 500) is True
    assert active_installation_for(user.id, "octo") is None
    assert list_installations(user.id) == []
    assert len(list_installations(user.id, include_revoked=True)) == 1


def test_revoking_twice_reports_nothing_to_do(temp_db):
    user = _user()
    save_installation(user.id, 500, "octo", "all")
    revoke_installation(user.id, 500)
    assert revoke_installation(user.id, 500) is False


def test_cannot_revoke_someone_elses_installation(temp_db):
    owner = _user(1, "octo")
    other = _user(2, "someone-else")
    save_installation(owner.id, 500, "octo", "all")
    assert revoke_installation(other.id, 500) is False
    assert active_installation_for(owner.id, "octo") is not None


def test_reinstalling_after_a_revoke_makes_it_usable_again(temp_db):
    user = _user()
    save_installation(user.id, 500, "octo", "all")
    revoke_installation(user.id, 500)
    save_installation(user.id, 500, "octo", "all")
    assert active_installation_for(user.id, "octo") is not None
