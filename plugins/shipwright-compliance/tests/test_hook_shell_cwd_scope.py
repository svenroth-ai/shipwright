"""A plain commit is judged on the project of the payload's shell directory (U13 follow-ups)."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts" / "lib"))
import rtm_commit_scope as rcs  # noqa: E402

if str(Path(__file__).parent) not in sys.path:  # sibling support module; tests/ is no package root
    sys.path.insert(0, str(Path(__file__).parent))
from rtm_hook_test_support import init_repo  # noqa: E402
from rtm_hook_test_support import scrub_git_env  # noqa: E402,F401 - autouse

pytestmark = pytest.mark.covers("FR-01.10")
needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")


# --- a plain commit is judged where the SHELL is ------------------------------------------

def _project(directory: Path) -> Path:
    (directory / ".shipwright" / "agent_docs").mkdir(parents=True)
    (directory / ".shipwright" / "compliance").mkdir(parents=True)
    (directory / ".shipwright" / "compliance" / "x.json").write_text("{}", encoding="utf-8")
    return directory


@needs_git
def test_a_plain_commit_uses_the_payload_directory_not_the_hook_process(tmp_path, monkeypatch):
    shell, hook = _project(tmp_path / "shell"), _project(tmp_path / "hook")
    init_repo(shell)
    init_repo(hook)
    monkeypatch.chdir(hook)  # the hook process runs in the OTHER project
    scope = rcs.commit_scope("git commit -m x", str(shell), lambda: str(hook))
    assert Path(scope.root) == shell
    inner = rcs.commit_scope('echo "$(git commit -m x)"', str(shell), lambda: str(hook))
    assert Path(inner.root) == shell


@needs_git
def test_a_shell_directory_with_nothing_to_measure_or_a_pinned_root_defers(tmp_path, monkeypatch):
    hook, fixture = _project(tmp_path / "hook"), _project(tmp_path / "fixture")
    for item in (fixture / ".shipwright" / "compliance").iterdir():
        item.unlink()  # a fixture project: nothing to measure
    scope = rcs.commit_scope("git commit -m x", str(fixture), lambda: str(hook))
    assert Path(scope.root) == hook
    shell = _project(tmp_path / "shell")
    monkeypatch.setenv("SHIPWRIGHT_PROJECT_ROOT", str(hook))  # the documented disambiguator
    assert Path(rcs.commit_scope("git commit -m x", str(shell), lambda: str(hook)).root) == hook
    other = _project(tmp_path / "other")  # env names C, cwd is B, no location: not B, not C
    monkeypatch.setenv("SHIPWRIGHT_PROJECT_ROOT", str(other))
    assert Path(rcs.commit_scope("git commit -m x", str(shell), lambda: str(hook)).root) == hook


def test_a_shell_directory_outside_any_project_falls_back_to_the_default(tmp_path):
    hook, elsewhere = _project(tmp_path / "hook"), tmp_path / "elsewhere"
    elsewhere.mkdir()
    init_repo(hook)
    scope = rcs.commit_scope("git commit -m x", str(elsewhere), lambda: str(hook))
    assert Path(scope.root) == hook
    missing = rcs.commit_scope("git commit -m x", str(tmp_path / "gone"), lambda: str(hook))
    assert Path(missing.root) == hook


@needs_git
def test_a_dropped_shell_project_or_missing_directory_says_so(tmp_path, monkeypatch):
    hook, shell = _project(tmp_path / "hook"), _project(tmp_path / "shell")
    monkeypatch.setenv("SHIPWRIGHT_PROJECT_ROOT", str(hook))
    scope = rcs.commit_scope("git commit -m x", str(shell), lambda: str(hook))
    assert Path(scope.root) == hook and any("SHIPWRIGHT_PROJECT_ROOT" in w for w in scope.warnings)
    gone = rcs.commit_scope("git commit -m x", str(tmp_path / "gone"), lambda: str(hook))
    assert any("does not exist" in w and str(hook) in w for w in gone.warnings)  # names both
    assert any(str(shell) in w and str(hook) in w for w in scope.warnings)


@needs_git
def test_a_pinned_root_naming_the_shell_project_keeps_it(tmp_path, monkeypatch):
    hook, shell = _project(tmp_path / "hook"), _project(tmp_path / "shell")
    monkeypatch.setenv("SHIPWRIGHT_PROJECT_ROOT", str(shell))
    scope = rcs.commit_scope("git commit -m x", str(shell), lambda: str(hook))
    assert Path(scope.root) == shell


def test_a_project_without_compliance_data_defers_with_a_warn(tmp_path):
    hook, fixture = _project(tmp_path / "hook"), _project(tmp_path / "fixture")
    for item in (fixture / ".shipwright" / "compliance").iterdir():
        item.unlink()
    scope = rcs.commit_scope("git commit -m x", str(fixture), lambda: str(hook))
    assert Path(scope.root) == hook
    assert any("holds no compliance data" in w for w in scope.warnings)


def test_a_project_found_below_the_shell_directory_is_not_the_commits_repo(tmp_path):
    hook = _project(tmp_path / "hook")
    examples = tmp_path / "repo" / "examples"
    demo = _project(examples / "demo")  # the only project below the shell directory
    (demo / "shipwright_run_config.json").write_text("{}", encoding="utf-8")
    assert rcs.project_at(examples)[1]  # it IS resolved by descent ...
    scope = rcs.commit_scope("git commit -m x", str(examples), lambda: str(hook))
    assert Path(scope.root) == hook  # never the nested demo the commit does not land in
