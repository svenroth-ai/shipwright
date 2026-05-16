"""Unit tests for shared/scripts/lib/worktree_isolation.py.

Exercises the in-process API: worktree detection, main-repo resolution,
the main-tree snapshot, leak detection, and the run pointer.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from lib.worktree_isolation import (
    IsolationError,
    default_branch,
    detect_leak,
    is_under_worktrees,
    is_worktree,
    main_repo_root,
    main_tree_status_paths,
    prune_stale_run_pointers,
    read_run_pointer,
    read_snapshot,
    write_run_pointer,
    write_snapshot,
)


def _add_worktree(work: Path, slug: str) -> Path:
    """Create a linked worktree under .worktrees/<slug> from local main."""
    wt = work / ".worktrees" / slug
    subprocess.run(
        [
            "git", "-C", str(work), "worktree", "add", str(wt),
            "-b", f"iterate/{slug}", "main",
        ],
        capture_output=True, text=True, check=True,
    )
    return wt


def test_is_worktree_false_for_main_repo(git_origin_repo):
    work, _ = git_origin_repo
    assert is_worktree(work) is False


def test_is_worktree_true_for_linked_worktree(git_origin_repo):
    work, _ = git_origin_repo
    wt = _add_worktree(work, "probe")
    assert is_worktree(wt) is True


def test_main_repo_root_from_worktree(git_origin_repo):
    work, _ = git_origin_repo
    wt = _add_worktree(work, "probe")
    assert main_repo_root(wt).resolve() == work.resolve()


def test_default_branch_resolves_main(git_origin_repo):
    work, _ = git_origin_repo
    assert default_branch(work) == "main"


def test_default_branch_override_wins(git_origin_repo):
    work, _ = git_origin_repo
    assert default_branch(work, override="trunk") == "trunk"


def test_is_under_worktrees(git_origin_repo):
    work, _ = git_origin_repo
    wt = _add_worktree(work, "probe")
    assert is_under_worktrees(wt, work) is True
    assert is_under_worktrees(work, work) is False


def test_main_tree_status_paths_excludes_run_infra(git_origin_repo):
    work, _ = git_origin_repo
    (work / "leaked.txt").write_text("x", encoding="utf-8")
    runs = work / ".shipwright" / "runs" / "r1"
    runs.mkdir(parents=True)
    (runs / "snap.json").write_text("{}", encoding="utf-8")
    paths = main_tree_status_paths(work)
    assert "leaked.txt" in paths
    assert not any(p.startswith(".shipwright/runs") for p in paths)


def test_snapshot_round_trip(git_origin_repo):
    work, _ = git_origin_repo
    (work / "dirty.txt").write_text("x", encoding="utf-8")
    write_snapshot(work, "iterate-x")
    snap = read_snapshot(work, "iterate-x")
    assert snap["run_id"] == "iterate-x"
    assert "dirty.txt" in snap["dirty_paths"]


def test_read_snapshot_missing_raises(git_origin_repo):
    work, _ = git_origin_repo
    with pytest.raises(IsolationError):
        read_snapshot(work, "no-such-run")


def test_detect_leak_clean(git_origin_repo):
    work, _ = git_origin_repo
    write_snapshot(work, "run-a")
    clean, new = detect_leak(work, "run-a")
    assert clean is True
    assert new == []


def test_detect_leak_flags_new_path(git_origin_repo):
    work, _ = git_origin_repo
    write_snapshot(work, "run-a")
    (work / "leaked.txt").write_text("x", encoding="utf-8")
    clean, new = detect_leak(work, "run-a")
    assert clean is False
    assert "leaked.txt" in new


def test_detect_leak_tolerates_preexisting(git_origin_repo):
    work, _ = git_origin_repo
    (work / "preexisting.txt").write_text("x", encoding="utf-8")
    write_snapshot(work, "run-a")  # snapshot captures the pre-existing dirt
    clean, new = detect_leak(work, "run-a")
    assert clean is True
    assert new == []


def test_run_pointer_round_trip(git_origin_repo):
    work, _ = git_origin_repo
    write_run_pointer(
        work,
        run_id="run-a",
        slug="a",
        branch="iterate/a",
        worktree_path=work / ".worktrees" / "a",
        session_id="sess-123",
    )
    ptr = read_run_pointer(work, "sess-123")
    assert ptr is not None
    assert ptr["run_id"] == "run-a"
    assert ptr["branch"] == "iterate/a"
    assert ptr["session_id"] == "sess-123"
    assert read_run_pointer(work, "other-sess") is None


def test_prune_stale_run_pointers(tmp_path):
    live_wt = tmp_path / "live"
    live_wt.mkdir()
    write_run_pointer(
        tmp_path, run_id="r-live", slug="live", branch="iterate/live",
        worktree_path=live_wt, session_id="sess-live",
    )
    write_run_pointer(
        tmp_path, run_id="r-dead", slug="dead", branch="iterate/dead",
        worktree_path=tmp_path / "gone", session_id="sess-dead",
    )
    removed = prune_stale_run_pointers(tmp_path)
    assert removed == 1
    assert read_run_pointer(tmp_path, "sess-live") is not None  # worktree exists
    assert read_run_pointer(tmp_path, "sess-dead") is None      # pruned


def _bare_repo(tmp_path: Path) -> Path:
    """A git repo whose .shipwright/ is NOT tracked — exercises git's
    untracked-directory collapsing (the M3 leak-guard edge case)."""
    repo = tmp_path / "bare-sw"
    repo.mkdir()
    env = os.environ.copy()
    env.update({
        "GIT_AUTHOR_NAME": "T", "GIT_AUTHOR_EMAIL": "t@t.invalid",
        "GIT_COMMITTER_NAME": "T", "GIT_COMMITTER_EMAIL": "t@t.invalid",
    })
    (repo / "README.md").write_text("x\n", encoding="utf-8")
    for args in (["init", "-b", "main"], ["add", "-A"], ["commit", "-m", "init"]):
        subprocess.run(
            ["git", *args], cwd=str(repo), env=env,
            capture_output=True, text=True, check=True,
        )
    return repo


def test_main_tree_status_paths_expands_untracked_shipwright(tmp_path):
    """When .shipwright/ is fully untracked git collapses it to one entry;
    the leak-guard must still see run-infra (excluded) vs a real leak."""
    repo = _bare_repo(tmp_path)
    (repo / ".shipwright" / "runs" / "r1").mkdir(parents=True)
    (repo / ".shipwright" / "runs" / "r1" / "snap.json").write_text(
        "{}", encoding="utf-8"
    )
    (repo / ".shipwright" / "agent_docs").mkdir(parents=True)
    (repo / ".shipwright" / "agent_docs" / "leak.md").write_text(
        "x", encoding="utf-8"
    )
    paths = main_tree_status_paths(repo)
    assert not any(p.startswith(".shipwright/runs") for p in paths)
    assert ".shipwright/agent_docs/leak.md" in paths
