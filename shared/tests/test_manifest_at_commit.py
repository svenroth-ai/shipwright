"""Tests for shared/scripts/lib/manifest_at_commit.py — the commit-pinned
manifest read P3.4c shares between the HEAD read (``promote_required_layers.
_read_committed_manifest``) and the anchor read."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from lib.manifest_at_commit import ManifestReadError, read_manifest_at_commit, resolve_head_sha


def _git(cwd: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(cwd), *args], capture_output=True, text=True, shell=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git {args} failed: {result.stderr}")
    return result.stdout


def _init_repo_with_manifest(tmp_path, manifest: dict) -> Path:
    (tmp_path / ".shipwright" / "compliance").mkdir(parents=True)
    (tmp_path / ".shipwright" / "compliance" / "test-traceability.json").write_text(
        json.dumps(manifest), encoding="utf-8",
    )
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "test@example.com")
    _git(tmp_path, "config", "user.name", "test")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "init")
    return tmp_path


def test_resolve_head_sha_returns_the_current_commit(tmp_path):
    project = _init_repo_with_manifest(tmp_path, {"requirements": {}})
    sha = resolve_head_sha(project)
    assert sha == _git(project, "rev-parse", "HEAD").strip()


def test_resolve_head_sha_raises_outside_a_git_repo(tmp_path):
    with pytest.raises(ManifestReadError):
        resolve_head_sha(tmp_path)


def test_read_manifest_at_commit_reads_the_exact_commit_not_the_working_tree(tmp_path):
    project = _init_repo_with_manifest(tmp_path, {"requirements": {"01::FR-01.01": {"id": "FR-01.01"}}})
    sha = resolve_head_sha(project)

    # Mutate the working tree after the commit -- the read must still see
    # the COMMITTED content, never this.
    (project / ".shipwright" / "compliance" / "test-traceability.json").write_text(
        json.dumps({"requirements": {}}), encoding="utf-8",
    )

    manifest = read_manifest_at_commit(project, sha)
    assert "01::FR-01.01" in manifest["requirements"]


def test_read_manifest_at_commit_raises_on_a_commit_with_no_such_path(tmp_path):
    project = _init_repo_with_manifest(tmp_path, {"requirements": {}})
    sha = resolve_head_sha(project)
    with pytest.raises(ManifestReadError):
        read_manifest_at_commit(project, sha, relpath="does/not/exist.json")


def test_read_manifest_at_commit_raises_on_invalid_json(tmp_path):
    (tmp_path / "manifest.json").write_text("not json", encoding="utf-8")
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "test@example.com")
    _git(tmp_path, "config", "user.name", "test")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "init")
    sha = resolve_head_sha(tmp_path)
    with pytest.raises(ManifestReadError):
        read_manifest_at_commit(tmp_path, sha, relpath="manifest.json")


def test_read_manifest_at_commit_raises_on_a_non_sha_commit_without_running_git(tmp_path):
    # External code review, low: `sha` reaches `git show f"{sha}:{relpath}"`
    # with no injection guard otherwise -- a value starting with `-` would
    # be parsed as a git option. Validated the same way
    # `ci_provenance._COMMIT_RE` already validates its own `commit` argument.
    project = _init_repo_with_manifest(tmp_path, {"requirements": {}})
    with pytest.raises(ManifestReadError):
        read_manifest_at_commit(project, "--output=/tmp/pwned")


def test_read_manifest_at_commit_raises_when_the_content_is_not_a_json_object(tmp_path):
    # Valid JSON, but the wrong shape -- a JSON array (or any non-object)
    # must be rejected the same way invalid JSON is, not silently accepted
    # as a manifest with no `requirements` key.
    (tmp_path / "manifest.json").write_text("[1, 2, 3]", encoding="utf-8")
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "test@example.com")
    _git(tmp_path, "config", "user.name", "test")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "init")
    sha = resolve_head_sha(tmp_path)
    with pytest.raises(ManifestReadError):
        read_manifest_at_commit(tmp_path, sha, relpath="manifest.json")
