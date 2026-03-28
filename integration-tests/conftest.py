"""Shared fixtures for integration tests."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

# Plugin roots
REPO_ROOT = Path(__file__).resolve().parent.parent
PROJECT_PLUGIN = REPO_ROOT / "plugins" / "shipwright-project"
PLAN_PLUGIN = REPO_ROOT / "plugins" / "shipwright-plan"
BUILD_PLUGIN = REPO_ROOT / "plugins" / "shipwright-build"
SHARED_SCRIPTS = REPO_ROOT / "shared" / "scripts"

FIXTURES = Path(__file__).resolve().parent / "fixtures"

# Make shared tools importable
if str(SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SHARED_SCRIPTS))


def run_shared_script(subdir: str, script_name: str, args: list[str]) -> str:
    """Run a shared script and return stdout."""
    script = str(SHARED_SCRIPTS / subdir / script_name)
    result = subprocess.run(
        [sys.executable, script] + args,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if result.returncode != 0 and not result.stdout.strip():
        raise RuntimeError(
            f"Script {script_name} failed (exit {result.returncode}): {result.stderr}"
        )
    return result.stdout


def run_script(plugin_dir: Path, subdir: str, script_name: str, args: list[str]) -> dict:
    """Run a plugin script and return parsed JSON output."""
    script = str(plugin_dir / "scripts" / subdir / script_name)
    result = subprocess.run(
        [sys.executable, script] + args,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if result.returncode != 0 and not result.stdout.strip():
        raise RuntimeError(
            f"Script {script_name} failed (exit {result.returncode}): {result.stderr}"
        )
    return json.loads(result.stdout)


@pytest.fixture
def mini_requirements():
    """Path to the mini-requirements fixture."""
    return FIXTURES / "mini-requirements.md"


@pytest.fixture
def trilogy_project(tmp_path, mini_requirements):
    """Set up a full project directory simulating the trilogy flow."""
    # Create project structure
    project = tmp_path / "todo-app"
    project.mkdir()
    planning = project / "planning"
    planning.mkdir()

    # Copy requirements into planning dir
    req = planning / "requirements.md"
    req.write_text(mini_requirements.read_text(encoding="utf-8"), encoding="utf-8")

    # Init git repo (needed for build plugin)
    subprocess.run(
        ["git", "init", "-b", "main"],
        cwd=str(project),
        capture_output=True,
        encoding="utf-8",
    )
    subprocess.run(
        ["git", "add", "."],
        cwd=str(project),
        capture_output=True,
        encoding="utf-8",
    )
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=str(project),
        capture_output=True,
        encoding="utf-8",
    )

    return project
