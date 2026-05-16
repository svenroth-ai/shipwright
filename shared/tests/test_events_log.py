"""Unit tests for shared/scripts/lib/events_log.py.

Exercises worktree-aware resolution of shipwright_events.jsonl against a
REAL ``git worktree`` layout (not mocks) — per external review the
common-dir math must be verified on an actual linked worktree.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from lib.events_log import EVENT_FILE, resolve_events_path


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


def test_main_repo_identity(git_origin_repo):
    """In the main repo the resolved path is project_root / EVENT_FILE."""
    work, _ = git_origin_repo
    resolved = resolve_events_path(work)
    assert resolved.resolve() == (work / EVENT_FILE).resolve()


def test_worktree_resolves_to_main_log(git_origin_repo):
    """From inside a linked worktree the log resolves to the MAIN repo —
    NOT the throwaway worktree copy that `git worktree remove` discards."""
    work, _ = git_origin_repo
    wt = _add_worktree(work, "probe")
    resolved = resolve_events_path(wt)
    assert resolved.resolve() == (work / EVENT_FILE).resolve()
    assert resolved.resolve() != (wt / EVENT_FILE).resolve()
    # The owning directory is the main repo root, not the worktree.
    assert resolved.parent.resolve() == work.resolve()


def test_worktree_nested_path_resolved(git_origin_repo):
    """A worktree several levels under .worktrees/ still resolves cleanly
    (relative `--git-common-dir` output with `..` segments)."""
    work, _ = git_origin_repo
    wt = _add_worktree(work, "deep-slug")
    resolved = resolve_events_path(wt)
    assert resolved.resolve() == (work / EVENT_FILE).resolve()


def test_non_git_dir_silent_fallback(tmp_path, recwarn):
    """A non-git directory falls back to project_root/EVENT_FILE SILENTLY:
    `git rev-parse` returncode!=0 is a definitive 'not a repo', not a
    failure — warning here would spam every non-git project."""
    resolved = resolve_events_path(tmp_path)
    assert resolved == tmp_path / EVENT_FILE
    assert len(recwarn) == 0


def test_git_unavailable_warns_then_falls_back(tmp_path, monkeypatch):
    """A broken/absent git binary emits a diagnostic before falling back —
    silent data loss in a worktree run must be visible (review openai#4)."""
    def _boom(*_args, **_kwargs):
        raise OSError("git: command not found")

    monkeypatch.setattr(subprocess, "run", _boom)
    with pytest.warns(UserWarning, match="git unavailable"):
        resolved = resolve_events_path(tmp_path)
    assert resolved == tmp_path / EVENT_FILE


def test_git_timeout_warns_then_falls_back(tmp_path, monkeypatch):
    """A hung git invocation (TimeoutExpired) also warns before fallback."""
    def _hang(*_args, **_kwargs):
        raise subprocess.TimeoutExpired(cmd="git", timeout=15.0)

    monkeypatch.setattr(subprocess, "run", _hang)
    with pytest.warns(UserWarning, match="git unavailable"):
        resolved = resolve_events_path(tmp_path)
    assert resolved == tmp_path / EVENT_FILE


def test_empty_common_dir_warns_then_falls_back(tmp_path, monkeypatch):
    """returncode 0 but empty stdout (a degenerate git result) → warn + fallback."""
    def _empty(*_args, **_kwargs):
        return subprocess.CompletedProcess(
            args=["git"], returncode=0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", _empty)
    with pytest.warns(UserWarning, match="empty output"):
        resolved = resolve_events_path(tmp_path)
    assert resolved == tmp_path / EVENT_FILE


def test_non_dotgit_common_dir_warns_then_falls_back(tmp_path, monkeypatch):
    """A git-common-dir not ending in `.git` (unexpected layout) → warn + fallback."""
    weird = str(tmp_path / "weird-admin-dir")

    def _weird(*_args, **_kwargs):
        return subprocess.CompletedProcess(
            args=["git"], returncode=0, stdout=weird + "\n", stderr="")

    monkeypatch.setattr(subprocess, "run", _weird)
    with pytest.warns(UserWarning, match="unexpected git-common-dir"):
        resolved = resolve_events_path(tmp_path)
    assert resolved == tmp_path / EVENT_FILE


def test_git_discovery_env_overrides_are_stripped(git_origin_repo, monkeypatch):
    """GIT_DIR / GIT_COMMON_DIR / GIT_WORK_TREE must NOT leak into the git
    invocation — otherwise resolution silently targets a different repo."""
    work, _ = git_origin_repo
    bogus = str(work / "bogus.git")
    monkeypatch.setenv("GIT_DIR", bogus)
    monkeypatch.setenv("GIT_COMMON_DIR", bogus)
    monkeypatch.setenv("GIT_WORK_TREE", str(work / "bogus-tree"))
    # With the overrides stripped, resolution still pins to `work`.
    resolved = resolve_events_path(work)
    assert resolved.resolve() == (work / EVENT_FILE).resolve()


def test_str_project_root_accepted(git_origin_repo):
    """Accepts a str project_root, not only a Path."""
    work, _ = git_origin_repo
    resolved = resolve_events_path(str(work))
    assert resolved.resolve() == (work / EVENT_FILE).resolve()
