"""Shared test fixtures."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

# Add shared scripts to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))


_OSS_SCANNERS = ("semgrep", "trivy", "gitleaks")


@pytest.fixture(autouse=True)
def _isolate_scanner_environment(monkeypatch):
    """No-op safety net for the orchestrator path.

    Iterate sec-report-and-orchestrator-decouple (2026) removed
    `_check_security_available()`. The env-clearing here is now defensive:
    ensures AIKIDO_CLIENT_ID and any future scanner-related env vars don't
    leak from the host into shared-test assertions. Mirror of fixtures in
    plugins/shipwright-run/tests/conftest.py + integration-tests/conftest.py.
    """
    monkeypatch.delenv("AIKIDO_CLIENT_ID", raising=False)
    monkeypatch.delenv("SHIPWRIGHT_SCANNER_BACKEND", raising=False)
    monkeypatch.setenv("SHIPWRIGHT_TEST_DISABLE_OSS_SCANNERS", "1")
    real_which = shutil.which

    def _which_no_oss(cmd, *args, **kwargs):
        if cmd in _OSS_SCANNERS:
            return None
        return real_which(cmd, *args, **kwargs)

    monkeypatch.setattr(shutil, "which", _which_no_oss)


@pytest.fixture
def tmp_project(tmp_path):
    """Create a temporary project directory with .shipwright/agent_docs/."""
    agent_docs = tmp_path / ".shipwright" / "agent_docs"
    agent_docs.mkdir(parents=True, exist_ok=True)
    return tmp_path


@pytest.fixture
def project_with_configs(tmp_project):
    """Create a temporary project with sample config files."""
    run_config = {
        "scope": "full_app",
        "profile": "supabase-nextjs",
        "autonomy_level": 2,
        "current_step": "build",
        "completed_steps": ["project", "design", "plan"],
        "completed_splits": ["01-auth"],
        "pipeline": ["project", "design", "plan", "build", "test", "changelog", "deploy"],
    }
    project_config = {
        "status": "complete",
        "splits": [
            {"name": "01-auth", "status": "complete"},
            {"name": "02-dashboard", "status": "in_progress"},
        ],
    }
    plan_config = {
        "status": "complete",
        "split": "02-dashboard",
    }
    build_config = {
        "sections": [
            {"name": "01-layout", "status": "complete", "commit": "abc1234"},
            {"name": "02-widgets", "status": "in_progress"},
        ],
    }

    for name, data in [
        ("shipwright_run_config.json", run_config),
        ("shipwright_project_config.json", project_config),
        ("shipwright_plan_config.json", plan_config),
        ("shipwright_build_config.json", build_config),
    ]:
        (tmp_project / name).write_text(json.dumps(data, indent=2), encoding="utf-8")

    return tmp_project


@pytest.fixture
def git_origin_repo(tmp_path):
    """A git working clone with a local bare 'origin' remote + one commit.

    Returns ``(work, origin)`` Paths. ``work`` is the MAIN repo working tree
    for worktree-isolation tests; ``.worktrees/<slug>`` children are created
    under it. ``origin`` is a local bare repo so ``git fetch origin`` works
    fully offline.

    ``.shipwright/`` is committed (``.gitkeep``) so the repo mirrors a real
    Shipwright project — where ``.shipwright/`` always carries tracked content.
    Without that, git collapses an untracked ``.shipwright/`` into a single
    ``?? .shipwright/`` status entry and the leak-guard's run-infra exclusion
    (which keys on ``.shipwright/runs/`` etc.) cannot see inside it.
    """
    env = os.environ.copy()
    env.update(
        {
            "GIT_AUTHOR_NAME": "Iso Test",
            "GIT_AUTHOR_EMAIL": "iso@test.invalid",
            "GIT_COMMITTER_NAME": "Iso Test",
            "GIT_COMMITTER_EMAIL": "iso@test.invalid",
        }
    )

    def _git(cwd, *args):
        return subprocess.run(
            ["git", *args],
            cwd=str(cwd),
            env=env,
            capture_output=True,
            text=True,
            check=True,
        )

    origin = tmp_path / "origin.git"
    work = tmp_path / "work"
    _git(tmp_path, "init", "--bare", "-b", "main", str(origin))
    _git(tmp_path, "clone", str(origin), str(work))
    (work / "README.md").write_text("hello\n", encoding="utf-8")
    shipwright_dir = work / ".shipwright"
    shipwright_dir.mkdir()
    (shipwright_dir / ".gitkeep").write_text("", encoding="utf-8")
    _git(work, "add", "-A")
    _git(work, "commit", "-m", "init")
    _git(work, "push", "origin", "main")
    _git(work, "remote", "set-head", "origin", "main")
    return work, origin


@pytest.fixture
def make_worktree():
    """Factory: ``make_worktree(work, slug)`` adds a linked git worktree.

    Creates ``<work>/.worktrees/<slug>`` on branch ``iterate/<slug>`` from
    ``main`` and returns its path. Shared by every worktree-isolation test
    (events-log resolution, decision-drop resolution, finalization checks)
    so the ``git worktree add`` invocation lives in exactly one place.
    """
    def _make(work: Path, slug: str) -> Path:
        wt = work / ".worktrees" / slug
        subprocess.run(
            ["git", "-C", str(work), "worktree", "add", str(wt),
             "-b", f"iterate/{slug}", "main"],
            capture_output=True, text=True, check=True,
        )
        return wt

    return _make


@pytest.fixture
def remove_worktree():
    """Factory: ``remove_worktree(work, wt)`` tears a linked worktree down
    the way iterate F11 cleanup (``git worktree remove --force``) does."""
    def _remove(work: Path, wt: Path) -> None:
        subprocess.run(
            ["git", "-C", str(work), "worktree", "remove", "--force", str(wt)],
            capture_output=True, text=True, check=True,
        )

    return _remove
