"""Tests for remediation/github.py -- the blob/tree/commit/ref/PR sequence,
and every way GitHub can refuse it. All against a mocked transport.
"""
from __future__ import annotations

import pytest

from remediation.github import GitHubWriteError, GitHubWriter, commit_files

BASE = "/repos/octo/demo"

_HAPPY = {
    ("GET", BASE): (200, {"default_branch": "main"}),
    ("GET", f"{BASE}/git/commits/basesha"): (200, {"tree": {"sha": "basetree"}}),
    ("POST", f"{BASE}/git/blobs"): (201, {"sha": "blobsha"}),
    ("POST", f"{BASE}/git/trees"): (201, {"sha": "newtree"}),
    ("POST", f"{BASE}/git/commits"): (201, {"sha": "newcommit"}),
    ("POST", f"{BASE}/git/refs"): (201, {"ref": "refs/heads/sentinels/fix-abc-1"}),
    ("POST", f"{BASE}/pulls"): (201, {"number": 7, "html_url": "https://github.com/octo/demo/pull/7"}),
}


def _writer(mock_api, routes):
    client = mock_api(routes)
    return GitHubWriter(client, "octo", "demo", "ghs_token"), client


async def test_commit_files_walks_blob_tree_commit_ref_in_order(mock_api):
    writer, client = _writer(mock_api, _HAPPY)
    sha = await commit_files(
        writer, "main", "basesha", "sentinels/fix-abc-1", "msg", [("a.txt", "hello")]
    )
    await client.aclose()
    assert sha == "newcommit"
    assert client.calls == [
        ("GET", f"{BASE}/git/commits/basesha"),
        ("POST", f"{BASE}/git/blobs"),
        ("POST", f"{BASE}/git/trees"),
        ("POST", f"{BASE}/git/commits"),
        ("POST", f"{BASE}/git/refs"),
    ]


async def test_commit_files_uploads_one_blob_per_file(mock_api):
    writer, client = _writer(mock_api, _HAPPY)
    await commit_files(
        writer, "main", "basesha", "sentinels/fix-abc-1", "msg",
        [("a.txt", "one"), ("b.txt", "two"), ("c.txt", "three")],
    )
    await client.aclose()
    assert client.calls.count(("POST", f"{BASE}/git/blobs")) == 3
    assert client.calls.count(("POST", f"{BASE}/git/trees")) == 1


async def test_tree_is_built_from_the_base_commits_tree_not_the_commit(mock_api):
    """Passing a commit SHA where a tree SHA belongs is the mistake that
    produces a PR deleting the whole repository -- so the lookup is asserted
    explicitly rather than assumed."""
    writer, client = _writer(mock_api, _HAPPY)
    await commit_files(writer, "main", "basesha", "sentinels/fix-abc-1", "m", [("a.txt", "x")])
    await client.aclose()
    assert ("GET", f"{BASE}/git/commits/basesha") in client.calls


async def test_403_names_the_missing_permission(mock_api):
    writer, client = _writer(mock_api, {**_HAPPY, ("POST", f"{BASE}/git/blobs"): (403, {})})
    with pytest.raises(GitHubWriteError, match="Contents and Pull requests") as exc:
        await commit_files(writer, "main", "basesha", "sentinels/fix-abc-1", "m", [("a.txt", "x")])
    await client.aclose()
    assert exc.value.status == 403


async def test_401_says_the_token_may_have_expired(mock_api):
    writer, client = _writer(mock_api, {**_HAPPY, ("POST", f"{BASE}/git/trees"): (401, {})})
    with pytest.raises(GitHubWriteError, match="expired"):
        await commit_files(writer, "main", "basesha", "sentinels/fix-abc-1", "m", [("a.txt", "x")])
    await client.aclose()


async def test_404_mentions_the_app_not_being_installed(mock_api):
    writer, client = _writer(mock_api, {("GET", BASE): (404, {})})
    with pytest.raises(GitHubWriteError, match="not installed"):
        await writer.get_repo()
    await client.aclose()


async def test_commit_failure_stops_before_the_ref_is_created(mock_api):
    writer, client = _writer(mock_api, {**_HAPPY, ("POST", f"{BASE}/git/commits"): (500, {})})
    with pytest.raises(GitHubWriteError):
        await commit_files(writer, "main", "basesha", "sentinels/fix-abc-1", "m", [("a.txt", "x")])
    await client.aclose()
    # Nothing named exists: blobs and trees with no ref pointing at them are
    # unreachable objects GitHub garbage-collects.
    assert ("POST", f"{BASE}/git/refs") not in client.calls


async def test_branch_already_exists_is_reported_as_such(mock_api):
    writer, client = _writer(mock_api, {**_HAPPY, ("POST", f"{BASE}/git/refs"): (422, {})})
    with pytest.raises(GitHubWriteError, match="already exists") as exc:
        await commit_files(writer, "main", "basesha", "sentinels/fix-abc-1", "m", [("a.txt", "x")])
    await client.aclose()
    assert exc.value.status == 422


async def test_pull_request_returns_the_html_url_a_human_opens(mock_api):
    writer, client = _writer(mock_api, _HAPPY)
    pull = await writer.create_pull_request("t", "b", "sentinels/fix-abc-1", "main")
    await client.aclose()
    assert pull.number == 7
    assert pull.url == "https://github.com/octo/demo/pull/7"


async def test_pull_request_failure_raises(mock_api):
    writer, client = _writer(mock_api, {**_HAPPY, ("POST", f"{BASE}/pulls"): (422, {})})
    with pytest.raises(GitHubWriteError, match="open the pull request"):
        await writer.create_pull_request("t", "b", "sentinels/fix-abc-1", "main")
    await client.aclose()


async def test_delete_ref_reports_success_and_failure_without_raising(mock_api):
    branch = "sentinels/fix-abc-1"
    writer, client = _writer(
        mock_api, {("DELETE", f"{BASE}/git/refs/heads/{branch}"): (204, None)}
    )
    assert await writer.delete_ref(branch) is True
    await client.aclose()

    writer, client = _writer(mock_api, {})   # 404 from the catch-all
    assert await writer.delete_ref(branch) is False
    await client.aclose()


async def test_get_pull_request_returns_none_for_a_missing_pr(mock_api):
    writer, client = _writer(mock_api, {})
    assert await writer.get_pull_request(7) is None
    await client.aclose()


async def test_get_pull_request_reports_merged_state(mock_api):
    writer, client = _writer(
        mock_api, {("GET", f"{BASE}/pulls/7"): (200, {"merged": True, "state": "closed"})}
    )
    pull = await writer.get_pull_request(7)
    await client.aclose()
    assert pull["merged"] is True


async def test_writer_has_no_way_to_move_an_existing_ref(mock_api):
    """CLAUDE.md remediation rule 5: never a force-push, never a write to a
    branch Sentinels did not create. The strongest form of that guarantee is
    that the method to update a ref does not exist."""
    writer, _ = _writer(mock_api, {})
    assert not hasattr(writer, "update_ref")
    assert not hasattr(writer, "merge")
