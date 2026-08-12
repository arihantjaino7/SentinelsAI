"""Creating a branch, a commit, and a pull request without ever cloning the
repository (PLAN-v5 Stage B).

Git's object model is four kinds of thing, and GitHub exposes an endpoint per
kind. Understanding the four is the whole of this file:

  **blob**  — one file's bytes. No name, no path; just content and a SHA.
  **tree**  — a directory listing: names, modes, and the SHAs they point at.
  **commit**— a pointer to one tree, plus a parent, an author, a message.
  **ref**   — a *movable* name, like `refs/heads/main`, pointing at a commit.

A commit made by hand follows exactly that order, bottom-up: upload the new
file contents, describe the directory that contains them, wrap that in a
commit, then point a new branch name at it. Nothing overwrites anything —
each step creates a new immutable object, and only the last step (the ref)
introduces a name anyone will see.

A tiny standalone version of the same idea, no git involved:

    contents = {"a1": "hello"}          # blobs, keyed by content id
    listing  = {"greeting.txt": "a1"}   # a tree
    snapshot = {"tree": listing, "parent": None, "msg": "first"}
    branches = {"main": snapshot}       # a ref: a name pointing at a snapshot

`base_tree` is the one subtlety worth stating outright. Passing it means "the
repository as it already is, with these paths replaced" — without it, the new
tree would be the *only* thing in the commit, and the pull request would show
every other file in the repository as deleted.

Everything here is scoped by CLAUDE.md's remediation rules 4 and 5: create a
`sentinels/…` ref, never touch an existing one, never push to a default
branch, never merge, never force.
"""
from __future__ import annotations

from dataclasses import dataclass

import httpx

GITHUB_API = "https://api.github.com"

_HEADERS = {"Accept": "application/vnd.github+json"}


class GitHubWriteError(RuntimeError):
    """Any failed GitHub write. Carries the status code so `apply.py` can tell
    "you lack permission" (403) from "that branch already exists" (422) when
    deciding what to tell the user and what to clean up."""

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


@dataclass
class PullRequest:
    number: int
    url: str          # the html_url a human opens, not the API url


class GitHubWriter:
    """Every write Stage B makes, bound to one repository and one token.

    A class rather than loose functions because owner/repo/token are threaded
    through all seven calls, and the alternative is passing the same three
    arguments seven times and eventually passing them in the wrong order.
    """

    def __init__(self, client: httpx.AsyncClient, owner: str, repo: str, token: str) -> None:
        self.client = client
        self.owner = owner
        self.repo = repo
        self._auth = {**_HEADERS, "Authorization": f"Bearer {token}"}

    @property
    def _base(self) -> str:
        return f"{GITHUB_API}/repos/{self.owner}/{self.repo}"

    async def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        try:
            response = await self.client.request(
                method, f"{self._base}{path}", headers=self._auth, **kwargs
            )
        except httpx.HTTPError as exc:
            raise GitHubWriteError(f"Could not reach GitHub: {exc}") from exc
        return response

    @staticmethod
    def _explain(response: httpx.Response, what: str) -> GitHubWriteError:
        """One place that turns a status code into a sentence a user can act
        on. GitHub's own error bodies say things like "Not Found" for a
        permissions problem, which sends people looking for the wrong bug."""
        status = response.status_code
        if status == 401:
            return GitHubWriteError(
                f"GitHub rejected the installation token while trying to {what}. "
                "It may have expired — try again.",
                status,
            )
        if status == 403:
            return GitHubWriteError(
                f"The Sentinels App is not permitted to {what} on this repository. "
                "Check that the installation grants Contents and Pull requests write access.",
                status,
            )
        if status == 404:
            return GitHubWriteError(
                f"GitHub could not find the repository while trying to {what} — "
                "either it does not exist or the App is not installed on it.",
                status,
            )
        return GitHubWriteError(f"GitHub refused to {what} (HTTP {status}).", status)

    async def get_repo(self) -> dict:
        """Repository metadata — read for `default_branch`, which the branch
        check in `apply.py` compares against before any write happens."""
        response = await self._request("GET", "")
        if response.status_code != 200:
            raise self._explain(response, "read the repository")
        return response.json()

    async def get_commit_tree(self, commit_sha: str) -> str:
        """The tree SHA a commit points at.

        Needed because `create_tree`'s `base_tree` wants a *tree*, and every
        other part of this flow speaks in *commits*. They are different
        objects — a commit is a wrapper around a tree plus metadata — and
        passing one where the other belongs is the kind of mistake that
        produces a pull request deleting the entire repository.
        """
        response = await self._request("GET", f"/git/commits/{commit_sha}")
        if response.status_code != 200:
            raise self._explain(response, "read the base commit")
        return response.json()["tree"]["sha"]

    async def create_blob(self, content: str) -> str:
        """Upload one file's contents; get back the SHA git will call it.

        Content is sent as UTF-8 text. Every fixer in this project writes
        source files and config, never binaries, so there is no case where
        base64 would be needed — and asserting the encoding explicitly beats
        letting GitHub guess.
        """
        response = await self._request(
            "POST", "/git/blobs", json={"content": content, "encoding": "utf-8"}
        )
        if response.status_code != 201:
            raise self._explain(response, "upload a file")
        return response.json()["sha"]

    async def create_tree(self, base_tree: str, entries: list[dict]) -> str:
        """Describe the repository's file listing as it will be after the fix.

        `entries` is `[{path, mode, type, sha}]`. Mode `100644` is a normal
        non-executable file — the only mode any fixer here produces. `sha` of
        `None` on an entry means deletion, which no Stage A fixer emits, but
        the shape is passed through unchanged so a later one can.
        """
        response = await self._request(
            "POST", "/git/trees", json={"base_tree": base_tree, "tree": entries}
        )
        if response.status_code != 201:
            raise self._explain(response, "build the file tree")
        return response.json()["sha"]

    async def create_commit(self, message: str, tree_sha: str, parent_sha: str) -> str:
        """One commit, one parent. A single parent is what makes this a normal
        linear commit rather than a merge — Sentinels never merges anything
        (CLAUDE.md remediation rule 5)."""
        response = await self._request(
            "POST",
            "/git/commits",
            json={"message": message, "tree": tree_sha, "parents": [parent_sha]},
        )
        if response.status_code != 201:
            raise self._explain(response, "create the commit")
        return response.json()["sha"]

    async def create_ref(self, branch: str, commit_sha: str) -> None:
        """Point a *new* branch name at that commit.

        `POST /git/refs` creates and only creates. The update verb is
        `PATCH /git/refs/{ref}`, which this class does not implement at all —
        the guarantee that Sentinels never moves a branch it did not create is
        strongest when the code to move one does not exist.
        """
        response = await self._request(
            "POST", "/git/refs", json={"ref": f"refs/heads/{branch}", "sha": commit_sha}
        )
        if response.status_code == 422:
            raise GitHubWriteError(
                f"A branch named {branch!r} already exists in this repository.", 422
            )
        if response.status_code != 201:
            raise self._explain(response, "create the branch")

    async def delete_ref(self, branch: str) -> bool:
        """Remove a branch Sentinels just created. Best-effort cleanup for the
        window between "branch exists" and "PR failed to open" — without it, a
        failed apply leaves an orphan branch in someone's repository with no
        pull request explaining what it is.

        Returns False rather than raising: this runs while another error is
        already being reported, and a failed cleanup must not replace the real
        cause with a less useful one.
        """
        try:
            response = await self._request("DELETE", f"/git/refs/heads/{branch}")
        except GitHubWriteError:
            return False
        return response.status_code in (204, 200)

    async def create_pull_request(
        self, title: str, body: str, head: str, base: str
    ) -> PullRequest:
        """Open the pull request. `head` is the sentinels branch, `base` the
        branch it is proposed against — never the other way round."""
        response = await self._request(
            "POST",
            "/pulls",
            json={"title": title, "body": body, "head": head, "base": base},
        )
        if response.status_code != 201:
            raise self._explain(response, "open the pull request")
        data = response.json()
        return PullRequest(number=data["number"], url=data["html_url"])

    async def get_pull_request(self, number: int) -> dict | None:
        """Read one pull request's current state. `None` if it's gone.

        Used by `GET /scans/{id}/fix/applications` to answer "is this merged
        yet" with GitHub's answer rather than with what Sentinels last saw —
        Stage C's verification hangs off that field, so a stale `pr_open`
        would mean silently verifying nothing.
        """
        response = await self._request("GET", f"/pulls/{number}")
        if response.status_code == 404:
            return None
        if response.status_code != 200:
            raise self._explain(response, "read the pull request")
        return response.json()


async def commit_files(
    writer: GitHubWriter,
    base_branch: str,
    base_sha: str,
    branch: str,
    message: str,
    files: list[tuple[str, str]],
) -> str:
    """The whole blob → tree → commit → ref sequence, in order.

    `files` is `[(path, new_content)]`. `base_sha` is the commit the new branch
    grows from — resolved by the caller from `base_branch`, so this function
    never has to decide what "current" means.

    Returns the new commit's SHA. Raises `GitHubWriteError` at the first step
    that fails, having created only immutable objects up to that point: a blob
    or tree with no ref pointing at it is unreachable and gets garbage
    collected, so a failure before `create_ref` leaves nothing visible behind.
    """
    base_tree = await writer.get_commit_tree(base_sha)

    entries = []
    for path, content in files:
        blob_sha = await writer.create_blob(content)
        entries.append({"path": path, "mode": "100644", "type": "blob", "sha": blob_sha})

    tree_sha = await writer.create_tree(base_tree, entries)
    commit_sha = await writer.create_commit(message, tree_sha, base_sha)
    await writer.create_ref(branch, commit_sha)
    return commit_sha
