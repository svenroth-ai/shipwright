"""Shared fixtures for integration tests."""

import json
import shutil
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


# ---------------------------------------------------------------------------
# Scanner-availability isolation (autouse)
# ---------------------------------------------------------------------------
#
# orchestrator._check_security_available() returns True when any of
# (semgrep, trivy, gitleaks) is on PATH, OR when AIKIDO_CLIENT_ID /
# SHIPWRIGHT_SCANNER_BACKEND is set. CI workstations often have semgrep
# installed, which would silently insert the security phase into pipelines
# our integration tests walk — making the assertion order phase-by-phase
# non-deterministic per host.
#
# Iterate sec-report-and-orchestrator-decouple (2026): security is no longer
# an orchestrator phase, so this fixture is a **no-op safety net** for the
# orchestrator path. Kept in place because:
#   1. AIKIDO_CLIENT_ID still informs `aikidoClientIdPresent` (diagnostic);
#      clearing it prevents host env leaking into test assertions.
#   2. Future scanner-related env vars benefit from the existing contract.

_OSS_SCANNERS = ("semgrep", "trivy", "gitleaks")


@pytest.fixture(autouse=True)
def _isolate_scanner_environment(monkeypatch):
    monkeypatch.delenv("AIKIDO_CLIENT_ID", raising=False)
    monkeypatch.delenv("SHIPWRIGHT_SCANNER_BACKEND", raising=False)
    # Test-only kill-switch reaching subprocess invocations of orchestrator.py.
    # In-process callers of _check_security_available() are isolated by the
    # shutil.which monkeypatch below; the env var covers the subprocess case.
    monkeypatch.setenv("SHIPWRIGHT_TEST_DISABLE_OSS_SCANNERS", "1")

    real_which = shutil.which

    def _which_no_oss(cmd, *args, **kwargs):
        if cmd in _OSS_SCANNERS:
            return None
        return real_which(cmd, *args, **kwargs)

    monkeypatch.setattr(shutil, "which", _which_no_oss)


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
