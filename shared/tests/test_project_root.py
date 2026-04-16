"""Tests for shared/scripts/lib/project_root.py."""

from __future__ import annotations

import os
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
