"""Resolve which `(owner, repo, ref)` a scan's fix-plan/apply/verify pipeline
targets -- either parsed straight out of a repo scan's own GitHub URL, or
through the `scan_repo_links` row a URL scan gets once it's linked (PLAN-v5
Stage D).

Every module that used to call `parse_github_url(report.url)` directly
(`planning.py`, `apply.py`, `verify.py`'s `refresh_applications`) funnels
through `repo_target()` instead, so a linked URL scan behaves exactly like a
repo scan from that point on -- one place decides "where do I read/write
this scan's files", not three copies of the same branch.
"""
from __future__ import annotations

from models import ScanReport
from repo.fetch import parse_github_url
from storage.scan_links import get_scan_repo_link


class NoRepoTarget(ValueError):
    """Raised when a scan has neither a valid repo URL nor a linked
    repository -- a `ValueError` so every existing `except ValueError` catch
    site around the old direct `parse_github_url` calls keeps working
    unchanged."""


def repo_target(report: ScanReport) -> tuple[str, str, str | None]:
    """`(owner, repo, ref)` for this scan. `ref` is `None` when nothing pins
    one down, meaning "the repository's own default branch" to every caller
    -- the same convention a bare repo-scan URL (no `/tree/<ref>`) already
    carries.
    """
    if report.target_type == "repo":
        return parse_github_url(report.url)

    link = get_scan_repo_link(report.id)
    if link is None:
        raise NoRepoTarget(
            f"Scan {report.id!r} is a URL scan with no linked repository yet. "
            "Link one before planning, applying, or verifying a fix."
        )
    return link.owner, link.repo, link.ref
