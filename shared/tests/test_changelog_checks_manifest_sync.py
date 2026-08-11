"""Tests for changelog_checks.check_manifest_version_matches_tag — the
standing (WARNING-severity) detective check for declared published-package
manifest drift. Separate file from test_verifiers_test_changelog_deploy.py
so this addition doesn't grow that file past its bloat-baseline entry.

Uses a real throwaway git repo (the check reads committed blobs + tags via
subprocess, and mocking `tools.verifiers.changelog_checks.subprocess.run`
would not reach lib.manifest_sync_core's own subprocess calls).
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from lib.manifest_sync_core import git
from tools.verifiers.changelog_checks import check_manifest_version_matches_tag
from tools.verifiers.common import Severity


def _run(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    proc = git(root, *args)
    assert proc.returncode == 0, f"git {args} failed: {proc.stderr}"
    return proc


@pytest.fixture
def repo(tmp_path):
    _run(tmp_path, "init", "-q")
    _run(tmp_path, "config", "user.email", "test@example.com")
    _run(tmp_path, "config", "user.name", "Test")
    return tmp_path


def _write_config(root: Path, entries: list[dict]) -> None:
    (root / "shipwright_changelog_config.json").write_text(
        json.dumps({"published_manifests": entries}), encoding="utf-8"
    )


def _write_manifest(path: Path, version: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"name": "pkg", "version": version}), encoding="utf-8")


def _commit_and_tag(root: Path, tag: str) -> None:
    _run(root, "add", "-A")
    _run(root, "commit", "-q", "-m", f"release {tag}")
    _run(root, "tag", "-a", tag, "-m", tag)


def test_no_config_passes_as_noop(repo):
    r = check_manifest_version_matches_tag(repo)
    assert r.ok is True
    assert "no published manifests declared" in r.detail


def test_no_releases_yet_passes(repo):
    _write_config(repo, [{"path": "package.json", "format": "package_json"}])
    _write_manifest(repo / "package.json", "0.1.0")
    _run(repo, "add", "-A")
    _run(repo, "commit", "-q", "-m", "no tag yet")
    r = check_manifest_version_matches_tag(repo)
    assert r.ok is True
    assert "no releases yet" in r.detail.lower()


def test_matching_manifest_passes(repo):
    _write_config(repo, [{"path": "package.json", "format": "package_json"}])
    _write_manifest(repo / "package.json", "1.2.0")
    _commit_and_tag(repo, "v1.2.0")
    r = check_manifest_version_matches_tag(repo)
    assert r.ok is True
    assert "v1.2.0" in r.detail


def test_drifted_manifest_warns_not_errors(repo):
    """Descoped from ERROR to WARNING in Architecture Review reconciliation
    (iterate-2026-08-11-changelog-manifest-version-sync) — this check must
    not be a hard release-blocking invariant."""
    _write_config(repo, [{"path": "package.json", "format": "package_json"}])
    _write_manifest(repo / "package.json", "1.2.0")
    _commit_and_tag(repo, "v1.2.0")
    # A later, unrelated commit hand-edits the manifest away from the tag.
    _write_manifest(repo / "package.json", "1.3.0-dev")
    _run(repo, "add", "-A")
    _run(repo, "commit", "-q", "-m", "post-release dev bump")

    r = check_manifest_version_matches_tag(repo)

    assert r.ok is False
    assert r.severity == Severity.WARNING.value
    assert "1.2.0" in r.detail and "1.3.0-dev" in r.detail


def test_declared_manifest_missing_at_head_warns(repo):
    _write_config(repo, [{"path": "missing/package.json", "format": "package_json"}])
    _run(repo, "add", "-A")
    _run(repo, "commit", "-q", "-m", "declare only")
    _run(repo, "tag", "-a", "v1.0.0", "-m", "v1.0.0")

    r = check_manifest_version_matches_tag(repo)

    assert r.ok is False
    assert r.severity == Severity.WARNING.value
    assert "missing/package.json" in r.detail


def test_malformed_config_warns_not_errors(repo):
    (repo / "shipwright_changelog_config.json").write_text("{not json", encoding="utf-8")
    r = check_manifest_version_matches_tag(repo)
    assert r.ok is False
    assert r.severity == Severity.WARNING.value
