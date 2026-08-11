"""Git-integration tests for sync_release_manifests.py: staging, the
verify-commit gate against the COMMITTED blob (including the regression
case the whole card exists to close), the pre-existing-dirty-file guard,
and staging failure. Needs a real throwaway git repo per test.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))  # shared/

from scripts.lib.manifest_sync_core import git  # noqa: E402
from scripts.tools.sync_release_manifests import sync, verify_commit  # noqa: E402


def _run(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    proc = git(root, *args)
    assert proc.returncode == 0, f"git {args} failed: {proc.stderr}"
    return proc


@pytest.fixture
def repo(tmp_path):
    _run(tmp_path, "init", "-q")
    _run(tmp_path, "config", "user.email", "test@example.com")
    _run(tmp_path, "config", "user.name", "Test")
    (tmp_path / ".gitkeep").write_text("", encoding="utf-8")
    _run(tmp_path, "add", ".gitkeep")
    _run(tmp_path, "commit", "-q", "-m", "init")
    return tmp_path


def _write_config(root: Path, entries: list[dict]) -> None:
    (root / "shipwright_changelog_config.json").write_text(
        json.dumps({"published_manifests": entries}), encoding="utf-8"
    )


def _write_manifest(path: Path, version: str = "0.1.0") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"name": "pkg", "version": version}, indent=2) + "\n", encoding="utf-8")


def _commit_all(root: Path, message: str) -> str:
    _run(root, "add", "-A")
    _run(root, "commit", "-q", "-m", message)
    return _run(root, "rev-parse", "HEAD").stdout.strip()


def test_stage_returns_pathspec(repo):
    _write_config(repo, [{"path": "package.json", "format": "package_json"}])
    _write_manifest(repo / "package.json", version="0.1.0")
    _run(repo, "add", "-A")
    _run(repo, "commit", "-q", "-m", "declare manifest")

    result = sync(repo, "0.2.0", dry_run=False, stage=True)

    assert result["status"] == "ok"
    assert result["manifest_pathspec"] == ["package.json"]
    staged = _run(repo, "diff", "--cached", "--name-only").stdout.split()
    assert "package.json" in staged


def test_verify_commit_passes_when_write_landed_in_commit(repo, tmp_path):
    _write_config(repo, [{"path": "package.json", "format": "package_json"}])
    _write_manifest(repo / "package.json", version="0.1.0")
    _run(repo, "add", "-A")
    _run(repo, "commit", "-q", "-m", "declare")

    result_file = tmp_path / "result.json"
    sync_result = sync(repo, "0.3.0", dry_run=False, stage=True)
    result_file.write_text(json.dumps(sync_result), encoding="utf-8")
    sha = _commit_all(repo, "release 0.3.0")

    verify = verify_commit(repo, sha, "0.3.0", result_file)
    assert verify["status"] == "ok"


def test_verify_commit_catches_omitted_manifest_regression(repo, tmp_path):
    """The exact regression from the card: the manifest was written and a
    sync result recorded it, but it was never actually included in the
    release commit (e.g. an omitted pathspec). A worktree-only check would
    see the bumped file and pass; verify-commit must not."""
    _write_config(repo, [{"path": "package.json", "format": "package_json"}])
    _write_manifest(repo / "package.json", version="0.1.0")
    _run(repo, "add", "-A")
    _run(repo, "commit", "-q", "-m", "declare")

    result_file = tmp_path / "result.json"
    sync_result = sync(repo, "0.4.0", dry_run=False, stage=False)  # write, but never staged
    result_file.write_text(json.dumps(sync_result), encoding="utf-8")
    assert json.loads((repo / "package.json").read_text())["version"] == "0.4.0"  # worktree IS bumped

    # Release commit happens WITHOUT the manifest change (simulating an
    # omitted pathspec) — commit something unrelated instead.
    (repo / "unrelated.txt").write_text("release notes", encoding="utf-8")
    _run(repo, "add", "unrelated.txt")
    _run(repo, "commit", "-q", "-m", "release 0.4.0")
    sha = _run(repo, "rev-parse", "HEAD").stdout.strip()

    verify = verify_commit(repo, sha, "0.4.0", result_file)
    assert verify["status"] == "verify_mismatch"
    assert verify["path"] == "package.json"


def test_verify_commit_rejects_a_failed_syncs_own_result_file(repo, tmp_path):
    """Code-reviewer (Stage 2) high finding: a --result-file is written
    UNCONDITIONALLY, including on a failed sync (every failure branch
    records manifests: []). Reading only "manifests" would let a failed
    Step 5.4 -- e.g. manifest_dirty_before_sync, fixed, then the release
    resumed straight at Step 6 -- make verify-commit report ok with the
    no-manifests note, recreating the card's regression inside the gate's
    own state file."""
    _write_config(repo, [{"path": "package.json", "format": "package_json"}])
    _write_manifest(repo / "package.json", version="0.1.0")
    _run(repo, "add", "-A")
    _run(repo, "commit", "-q", "-m", "declare")

    # Unrelated dirty edit makes the sync fail closed before it ever writes.
    (repo / "package.json").write_text(
        json.dumps({"name": "pkg", "version": "0.1.0", "extra": "dirty"}), encoding="utf-8"
    )
    failed_result = sync(repo, "0.7.0", dry_run=False, stage=True)
    assert failed_result["status"] == "manifest_dirty_before_sync"

    result_file = tmp_path / "result.json"
    result_file.write_text(json.dumps(failed_result), encoding="utf-8")

    # Operator resolves the dirty state by committing it, then resumes at
    # Step 6 without re-running Step 5.4 -- package.json is still 0.1.0.
    _run(repo, "add", "-A")
    sha = _commit_all(repo, "release 0.7.0 (manifest never actually bumped)")

    verify = verify_commit(repo, sha, "0.7.0", result_file)
    assert verify["status"] == "sync_incomplete"


def test_verify_commit_rejects_a_stale_prior_releases_result_file(repo, tmp_path):
    """The result file lives at a fixed, non-run-scoped path that persists
    across releases. A leftover file from a PRIOR successful release must
    not be trusted to verify a DIFFERENT release's tag."""
    _write_config(repo, [{"path": "package.json", "format": "package_json"}])
    _write_manifest(repo / "package.json", version="0.1.0")
    _run(repo, "add", "-A")
    _run(repo, "commit", "-q", "-m", "declare")

    result_file = tmp_path / "result.json"
    stale_result = sync(repo, "0.8.0", dry_run=False, stage=True)
    assert stale_result["status"] == "ok"
    result_file.write_text(json.dumps(stale_result), encoding="utf-8")
    _commit_all(repo, "release 0.8.0")

    # A later release bumps the tag but this run's Step 5.4 never executed
    # (or its own write failed after producing no fresh result) -- the
    # stale 0.8.0 result file is still sitting at the fixed path.
    (repo / "unrelated.txt").write_text("release notes", encoding="utf-8")
    sha_later = _commit_all(repo, "release 0.9.0 (no manifest sync this time)")

    verify = verify_commit(repo, sha_later, "0.9.0", result_file)
    assert verify["status"] == "result_file_stale"


def test_verify_commit_resolves_subdirectory_project_root(repo, tmp_path):
    """--project-root can be a subdirectory of the git repo; verify-commit
    must resolve the git-relative path correctly, not assume the two roots
    coincide."""
    project_root = repo / "sub"
    project_root.mkdir()
    _write_config(project_root, [{"path": "package.json", "format": "package_json"}])
    _write_manifest(project_root / "package.json", version="0.1.0")
    _run(repo, "add", "-A")
    _run(repo, "commit", "-q", "-m", "declare")

    result_file = tmp_path / "result.json"
    sync_result = sync(project_root, "0.5.0", dry_run=False, stage=True)
    result_file.write_text(json.dumps(sync_result), encoding="utf-8")
    sha = _commit_all(repo, "release 0.5.0")

    verify = verify_commit(project_root, sha, "0.5.0", result_file)
    assert verify["status"] == "ok"


def test_verify_commit_ignores_config_mutated_after_sync(repo, tmp_path):
    """--verify-commit must never re-read shipwright_changelog_config.json —
    only Step 5.4's frozen --result-file. Prove it empirically: mutate (and
    then delete) the config after sync() ran, and confirm verify_commit
    still passes using the frozen manifest list."""
    _write_config(repo, [{"path": "package.json", "format": "package_json"}])
    _write_manifest(repo / "package.json", version="0.1.0")
    _run(repo, "add", "-A")
    _run(repo, "commit", "-q", "-m", "declare")

    result_file = tmp_path / "result.json"
    sync_result = sync(repo, "0.6.0", dry_run=False, stage=True)
    result_file.write_text(json.dumps(sync_result), encoding="utf-8")

    # Config edited to declare something else entirely, then removed —
    # neither should be visible to verify_commit.
    _write_config(repo, [{"path": "other.json", "format": "package_json"}])
    sha = _commit_all(repo, "release 0.6.0")
    (repo / "shipwright_changelog_config.json").unlink()

    verify = verify_commit(repo, sha, "0.6.0", result_file)
    assert verify["status"] == "ok"
    assert verify["manifests"] == [{"path": "package.json", "committed_version": "0.6.0"}]


def test_manifest_dirty_before_sync_fails_closed(repo):
    """A manifest with pre-existing uncommitted edits must not have those
    edits silently folded into the release commit via --stage."""
    _write_config(repo, [{"path": "package.json", "format": "package_json"}])
    _write_manifest(repo / "package.json", version="0.1.0")
    _run(repo, "add", "-A")
    _run(repo, "commit", "-q", "-m", "declare")

    # Unrelated pre-existing edit to the same file, never committed.
    (repo / "package.json").write_text(
        json.dumps({"name": "pkg", "version": "0.1.0", "description": "unrelated edit"}),
        encoding="utf-8",
    )

    result = sync(repo, "0.2.0", dry_run=False, stage=True)
    assert result["status"] == "manifest_dirty_before_sync"


def test_dirty_check_failure_fails_closed(repo, monkeypatch):
    """A `git status` that itself fails (index lock, damaged repo) must be
    treated as 'cannot confirm clean', not as 'not dirty' — the only
    fail-open branch a prior design left in an otherwise fail-closed tool."""
    _write_config(repo, [{"path": "package.json", "format": "package_json"}])
    _write_manifest(repo / "package.json", version="0.1.0")
    _run(repo, "add", "-A")
    _run(repo, "commit", "-q", "-m", "declare")

    import scripts.tools.sync_release_manifests as mod

    real_git = mod.git

    class _FailingStatus:
        returncode = 128
        stdout = ""
        stderr = "fatal: unable to read index"

    def flaky_git(root, *args):
        if args and args[0] == "status":
            return _FailingStatus()
        return real_git(root, *args)

    monkeypatch.setattr(mod, "git", flaky_git)

    result = sync(repo, "0.2.0", dry_run=False, stage=False)
    assert result["status"] == "manifest_dirty_before_sync"


def test_stage_failure_restores_written_bytes(repo, monkeypatch):
    """Doubt-reviewer D2: also asserts the defensive ``git reset`` runs
    against the declared paths before/alongside the byte restore, so a
    partial ``git add`` (a failure mode this mocked ``add`` can't itself
    reproduce, but reset must still cover) can't leave the index out of
    sync with the worktree bytes just restored underneath it."""
    _write_config(repo, [{"path": "package.json", "format": "package_json"}])
    _write_manifest(repo / "package.json", version="0.1.0")
    _run(repo, "add", "-A")
    _run(repo, "commit", "-q", "-m", "declare")
    original = (repo / "package.json").read_bytes()

    import scripts.tools.sync_release_manifests as mod

    class _FailingAdd:
        returncode = 1
        stderr = "simulated index lock"

    real_git = mod.git
    calls: list[tuple] = []

    def flaky_git(root, *args):
        calls.append(args)
        if args and args[0] == "add":
            return _FailingAdd()
        return real_git(root, *args)

    monkeypatch.setattr(mod, "git", flaky_git)

    result = sync(repo, "0.2.0", dry_run=False, stage=True)

    assert result["status"] == "stage_failed"
    assert (repo / "package.json").read_bytes() == original
    assert ("reset", "-q", "--", "package.json") in calls
