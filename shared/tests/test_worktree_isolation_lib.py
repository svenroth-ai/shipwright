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


def test_detect_leak_ignores_untracked_event_log(git_origin_repo):
    """F7 writes shipwright_events.jsonl into the MAIN tree by design (the
    event log is a repo-scoped journal). The leak-guard must NOT flag it —
    nor its .lock mutex — even when untracked."""
    work, _ = git_origin_repo
    write_snapshot(work, "run-a")
    (work / "shipwright_events.jsonl").write_text("{}\n", encoding="utf-8")
    (work / "shipwright_events.jsonl.lock").write_text("", encoding="utf-8")
    clean, new = detect_leak(work, "run-a")
    assert clean is True
    assert new == []


def test_detect_leak_ignores_tracked_event_log(git_origin_repo):
    """Same exemption when shipwright_events.jsonl is TRACKED — the
    Shipwright monorepo tracks it, so an F7 append shows as `M` not `??`."""
    work, _ = git_origin_repo
    (work / "shipwright_events.jsonl").write_text("{}\n", encoding="utf-8")
    subprocess.run(
        ["git", "-C", str(work), "add", "shipwright_events.jsonl"],
        capture_output=True, text=True, check=True,
    )
    subprocess.run(
        ["git", "-C", str(work), "-c", "user.name=t",
         "-c", "user.email=t@t.invalid", "commit", "-m", "track event log"],
        capture_output=True, text=True, check=True,
    )
    write_snapshot(work, "run-b")  # clean snapshot
    (work / "shipwright_events.jsonl").write_text(
        '{}\n{"x":1}\n', encoding="utf-8"
    )  # F7 appends → tracked file now modified
    clean, new = detect_leak(work, "run-b")
    assert clean is True
    assert new == []


def test_detect_leak_ignores_tracked_triage_log(git_origin_repo):
    """Campaign 2026-06-05-track-triage-jsonl: once .shipwright/triage.jsonl is
    tracked, background Stop-hook / triage_add appends to the MAIN backlog during
    an iterate are durable-log writes, not a leak — same exemption as events."""
    work, _ = git_origin_repo
    (work / ".shipwright").mkdir(exist_ok=True)
    (work / ".shipwright" / "triage.jsonl").write_text(
        '{"v":1,"schema":"triage"}\n', encoding="utf-8")
    subprocess.run(
        ["git", "-C", str(work), "add", ".shipwright/triage.jsonl"],
        capture_output=True, text=True, check=True,
    )
    subprocess.run(
        ["git", "-C", str(work), "-c", "user.name=t",
         "-c", "user.email=t@t.invalid", "commit", "-m", "track triage"],
        capture_output=True, text=True, check=True,
    )
    write_snapshot(work, "run-t")  # clean snapshot
    (work / ".shipwright" / "triage.jsonl").write_text(
        '{"v":1,"schema":"triage"}\n{"event":"append","id":"trg-1"}\n',
        encoding="utf-8",
    )  # a background-hook append → tracked file now modified
    clean, new = detect_leak(work, "run-t")
    assert clean is True
    assert new == []


def test_detect_leak_still_flags_event_log_in_subdir(git_origin_repo):
    """The exemption is an EXACT root-relative match: a same-named file in
    a subdirectory is NOT the canonical event log and is still a leak.

    `nested/` is committed first so git does not collapse the untracked
    directory into a single `nested/` status entry — the new file then
    surfaces as its own porcelain path.
    """
    work, _ = git_origin_repo
    nested = work / "nested"
    nested.mkdir()
    (nested / "keep.txt").write_text("x", encoding="utf-8")
    subprocess.run(
        ["git", "-C", str(work), "add", "nested/keep.txt"],
        capture_output=True, text=True, check=True,
    )
    subprocess.run(
        ["git", "-C", str(work), "-c", "user.name=t",
         "-c", "user.email=t@t.invalid", "commit", "-m", "track nested/"],
        capture_output=True, text=True, check=True,
    )
    write_snapshot(work, "run-c")
    (nested / "shipwright_events.jsonl").write_text("{}\n", encoding="utf-8")
    clean, new = detect_leak(work, "run-c")
    assert clean is False
    assert "nested/shipwright_events.jsonl" in new


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
