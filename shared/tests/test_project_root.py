"""Tests for shared/scripts/lib/project_root.py."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """Remove SHIPWRIGHT_PROJECT_ROOT so tests start clean."""
    monkeypatch.delenv("SHIPWRIGHT_PROJECT_ROOT", raising=False)


def _make_project(path: Path) -> None:
    """Create a minimal Shipwright project marker at *path*."""
    path.mkdir(parents=True, exist_ok=True)
    (path / "shipwright_run_config.json").write_text("{}", encoding="utf-8")


def test_cwd_is_project(tmp_path, monkeypatch):
    _make_project(tmp_path)
    monkeypatch.chdir(tmp_path)

    from lib.project_root import resolve_project_root
    assert resolve_project_root() == tmp_path


def test_single_subdirectory(tmp_path, monkeypatch):
    webui = tmp_path / "webui"
    _make_project(webui)
    monkeypatch.chdir(tmp_path)

    from lib.project_root import resolve_project_root
    assert resolve_project_root() == webui


def test_multiple_subdirectories_raises(tmp_path, monkeypatch):
    _make_project(tmp_path / "webui")
    _make_project(tmp_path / "api")
    monkeypatch.chdir(tmp_path)

    from lib.project_root import resolve_project_root
    with pytest.raises(ValueError, match="Multiple Shipwright projects"):
        resolve_project_root()


def test_standalone_fallback(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    from lib.project_root import resolve_project_root
    assert resolve_project_root() == tmp_path


def test_env_var_valid(tmp_path, monkeypatch):
    project = tmp_path / "myproject"
    _make_project(project)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SHIPWRIGHT_PROJECT_ROOT", str(project))

    from lib.project_root import resolve_project_root
    assert resolve_project_root() == project


def test_env_var_invalid_falls_through(tmp_path, monkeypatch):
    """ENV points to a dir without Shipwright markers — ignore it."""
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    webui = tmp_path / "webui"
    _make_project(webui)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SHIPWRIGHT_PROJECT_ROOT", str(empty_dir))

    from lib.project_root import resolve_project_root
    assert resolve_project_root() == webui


def test_env_var_disabled(tmp_path, monkeypatch):
    """allow_env=False skips the env var entirely."""
    project = tmp_path / "webui"
    _make_project(project)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SHIPWRIGHT_PROJECT_ROOT", str(project))

    from lib.project_root import resolve_project_root
    # With allow_env=False, it should still find webui via subdir scan
    assert resolve_project_root(allow_env=False) == project


def test_secondary_marker_detected(tmp_path, monkeypatch):
    """A project with only shipwright_events.jsonl (no run_config) is found."""
    project = tmp_path / "webui"
    project.mkdir()
    (project / "shipwright_events.jsonl").write_text("", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    from lib.project_root import resolve_project_root
    assert resolve_project_root() == project


def test_hidden_dirs_ignored(tmp_path, monkeypatch):
    """Directories starting with '.' are skipped during subdir scan."""
    hidden = tmp_path / ".shipwright-cache"
    _make_project(hidden)
    monkeypatch.chdir(tmp_path)

    from lib.project_root import resolve_project_root
    # Should not find .shipwright-cache, fall back to cwd
    assert resolve_project_root() == tmp_path


def _make_git_repo(path: Path) -> None:
    """Mark *path* as a git repository root (a bare ``.git`` dir is enough —
    the resolver only checks for its existence, never its contents)."""
    (path / ".git").mkdir(parents=True, exist_ok=True)


def test_subdirectory_of_project_walks_up_to_git_root(tmp_path, monkeypatch):
    """cwd=<repo>/server, repo root carries the markers — must resolve to the
    repo root, not to ``server/`` itself (the reported bug: a producer
    invoked with cwd set to an npm-workspace subdirectory wrote its durable
    artifacts into a second, untracked ``server/.shipwright/``)."""
    repo = tmp_path / "shipwright-webui"
    _make_project(repo)
    _make_git_repo(repo)
    server = repo / "server"
    server.mkdir()
    monkeypatch.chdir(server)

    from lib.project_root import resolve_project_root
    assert resolve_project_root() == repo


def test_deeply_nested_subdirectory_walks_up_to_git_root(tmp_path, monkeypatch):
    """Same as above, two levels deep (e.g. ``server/src/routes``)."""
    repo = tmp_path / "shipwright-webui"
    _make_project(repo)
    _make_git_repo(repo)
    nested = repo / "server" / "src" / "routes"
    nested.mkdir(parents=True)
    monkeypatch.chdir(nested)

    from lib.project_root import resolve_project_root
    assert resolve_project_root() == repo


def test_ancestor_walk_stops_at_git_boundary(tmp_path, monkeypatch):
    """An unrelated Shipwright project ABOVE the git root must never be
    picked up — the walk stops at (and includes) the repo boundary."""
    _make_project(tmp_path)  # outer project — must be ignored
    repo = tmp_path / "unrelated-repo"
    _make_git_repo(repo)
    nested = repo / "server"
    nested.mkdir(parents=True)
    monkeypatch.chdir(nested)

    from lib.project_root import resolve_project_root
    # repo itself carries no markers and is the walk's boundary — falls back
    # to cwd, never escapes to the outer tmp_path project.
    assert resolve_project_root() == nested


def test_ancestor_walk_finds_nearest_marker_before_git_root(tmp_path, monkeypatch):
    """Markers on an intermediate ancestor win over the git root itself."""
    repo = tmp_path / "repo"
    _make_git_repo(repo)
    project = repo / "apps" / "webui"
    _make_project(project)
    nested = project / "server"
    nested.mkdir()
    monkeypatch.chdir(nested)

    from lib.project_root import resolve_project_root
    assert resolve_project_root() == project


def test_nested_subdirectory_without_git_falls_back_to_cwd(tmp_path, monkeypatch):
    """No ``.git`` anywhere up the tree — unbounded ancestor walk is refused,
    keeping the pre-existing standalone-fallback behaviour intact."""
    repo = tmp_path / "shipwright-webui"
    _make_project(repo)
    server = repo / "server"
    server.mkdir()
    monkeypatch.chdir(server)

    from lib.project_root import resolve_project_root
    assert resolve_project_root() == server


def test_worktree_git_file_is_a_valid_boundary(tmp_path, monkeypatch):
    """A git worktree's ``.git`` is a FILE, not a directory — must still be
    honoured as the ancestor-walk boundary."""
    repo = tmp_path / "shipwright-webui"
    _make_project(repo)
    (repo / ".git").write_text("gitdir: /elsewhere/.git/worktrees/x\n", encoding="utf-8")
    server = repo / "server"
    server.mkdir()
    monkeypatch.chdir(server)

    from lib.project_root import resolve_project_root
    assert resolve_project_root() == repo
