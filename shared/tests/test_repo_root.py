"""Unit tests for shared/scripts/lib/repo_root.py.

Covers ``resolve_main_repo_root`` — the generic git-worktree-aware MAIN-repo-root
primitive behind the decision-drop resolvers, the iterate F11 verifier, the
plugin-sync Stop hook, and the compliance Group-F detective.

These tests moved here from ``test_events_log.py`` in
``iterate-2026-06-12-repo-root-resolver-relocate`` when the implementation was
relocated from ``lib/events_log.py`` to its thematic home ``lib/repo_root.py``.
The behaviour is verified against a REAL ``git worktree`` layout (not mocks) — the
common-dir math must hold on an actual linked worktree. The back-compat re-export
(``from lib.events_log import resolve_main_repo_root``) is pinned separately in
``test_events_log.py``.
"""

from __future__ import annotations

import subprocess

import pytest

from lib.repo_root import resolve_main_repo_root

# Linked worktrees are created via the shared ``make_worktree`` fixture
# (shared/tests/conftest.py).


def test_main_repo_root_git_discovery_env_overrides_are_stripped(git_origin_repo, monkeypatch):
    """GIT_DIR / GIT_COMMON_DIR / GIT_WORK_TREE must NOT leak into the git
    invocation in ``resolve_main_repo_root`` (the decision-drop primitive) —
    otherwise resolution silently targets a different repo."""
    work, _ = git_origin_repo
    bogus = str(work / "bogus.git")
    monkeypatch.setenv("GIT_DIR", bogus)
    monkeypatch.setenv("GIT_COMMON_DIR", bogus)
    monkeypatch.setenv("GIT_WORK_TREE", str(work / "bogus-tree"))
    # With the overrides stripped, resolution still pins to `work`.
    assert resolve_main_repo_root(work).resolve() == work.resolve()


def test_main_repo_root_plain_repo(git_origin_repo):
    """In a plain checkout the main-repo root is the repo root itself."""
    work, _ = git_origin_repo
    assert resolve_main_repo_root(work).resolve() == work.resolve()


def test_main_repo_root_from_worktree(git_origin_repo, make_worktree):
    """From inside a linked worktree it resolves to the MAIN repo root —
    NOT the ephemeral worktree that `git worktree remove` discards."""
    work, _ = git_origin_repo
    wt = make_worktree(work, "mrr-probe")
    assert resolve_main_repo_root(wt).resolve() == work.resolve()


def test_main_repo_root_non_git_returns_none_silently(tmp_path, recwarn):
    """A non-git directory yields None SILENTLY — `git rev-parse` returncode
    != 0 is a definitive 'not a repo', so callers fall back without a warning
    that would spam every non-git project."""
    assert resolve_main_repo_root(tmp_path) is None
    assert len(recwarn) == 0


def test_main_repo_root_git_unavailable_warns_then_none(tmp_path, monkeypatch):
    """A broken/absent git binary warns before returning None — silent data
    loss in a worktree run must stay visible. Exactly one diagnostic — a
    second would mean a duplicated warn path."""
    def _boom(*_args, **_kwargs):
        raise OSError("git: command not found")

    monkeypatch.setattr(subprocess, "run", _boom)
    with pytest.warns(UserWarning, match="git unavailable") as rec:
        assert resolve_main_repo_root(tmp_path) is None
    assert len(rec) == 1


def test_main_repo_root_str_project_root_accepted(git_origin_repo):
    """Accepts a str project_root, not only a Path."""
    work, _ = git_origin_repo
    assert resolve_main_repo_root(str(work)).resolve() == work.resolve()
