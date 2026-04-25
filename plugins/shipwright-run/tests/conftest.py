"""Shared test fixtures for shipwright-run."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "lib"))


_OSS_SCANNERS = ("semgrep", "trivy", "gitleaks")


@pytest.fixture(autouse=True)
def _isolate_scanner_environment(monkeypatch):
    """Make scanner availability deterministic for the test suite.

    Production behaviour: orchestrator._check_security_available() returns
    True if SHIPWRIGHT_SCANNER_BACKEND is set, OR AIKIDO_CLIENT_ID is set, OR
    any of (semgrep, trivy, gitleaks) is on PATH. The dev/CI host can have
    any of those installed (semgrep is common), which makes the security
    phase appear or disappear from `pipeline` non-deterministically across
    workstations.

    This autouse fixture clears all three signals at the start of every test
    so the default state is "no security backend". Tests that need security
    to be active opt in explicitly via monkeypatch.setenv("AIKIDO_CLIENT_ID",
    ...) or by patching shutil.which to return a path for one of the OSS
    tools.
    """
    monkeypatch.delenv("AIKIDO_CLIENT_ID", raising=False)
    monkeypatch.delenv("SHIPWRIGHT_SCANNER_BACKEND", raising=False)

    import shutil
    real_which = shutil.which

    def _which_no_oss(cmd, *args, **kwargs):
        if cmd in _OSS_SCANNERS:
            return None
        return real_which(cmd, *args, **kwargs)

    monkeypatch.setattr(shutil, "which", _which_no_oss)


@pytest.fixture
def plugin_root():
    return Path(__file__).resolve().parent.parent


@pytest.fixture
def tmp_project(tmp_path):
    """Create a temporary project directory."""
    project = tmp_path / "my-project"
    project.mkdir()
    return project


@pytest.fixture
def existing_project(tmp_project):
    """Project with CLAUDE.md and agent_docs (Extension scope)."""
    (tmp_project / "CLAUDE.md").write_text("# My Project\n")
    (tmp_project / "agent_docs").mkdir()
    (tmp_project / "agent_docs" / "architecture.md").write_text("# Arch\n")
    return tmp_project
