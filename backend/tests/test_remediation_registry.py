"""Tests for remediation/registry.py -- fixer dispatch."""
from __future__ import annotations

from models import Finding, Severity, Status
from remediation.dockerfile import DockerRootUserFixer
from remediation.gitignore import GitignoreFixer
from remediation.registry import fixer_for
from remediation.scaffolding import EnvExampleFixer, ReadmeFixer
from remediation.workflows import WorkflowPinFixer


def _finding(finding_id: str) -> Finding:
    return Finding(id=finding_id, title="t", category="c", severity=Severity.LOW, status=Status.WARN)


def test_fixer_for_dispatches_each_known_id_to_the_right_fixer():
    assert isinstance(fixer_for(_finding("ci-unpinned-action-x-L1")), WorkflowPinFixer)
    assert isinstance(fixer_for(_finding("gitignore-present")), GitignoreFixer)
    assert isinstance(fixer_for(_finding("repo-readme-present")), ReadmeFixer)
    assert isinstance(fixer_for(_finding("repo-env-example-present")), EnvExampleFixer)
    assert isinstance(fixer_for(_finding("docker-root-user-Dockerfile")), DockerRootUserFixer)


def test_fixer_for_returns_none_for_unrecognized_finding():
    assert fixer_for(_finding("spf-record")) is None
    assert fixer_for(_finding("totally-unknown-id")) is None
