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

    Iterate sec-report-and-orchestrator-decouple (2026): security is no
    longer an orchestrator phase, so `_check_security_available()` no longer
    exists and `freeze_run_conditions()` always returns
    `securityEnabled: False`. This fixture is therefore a **no-op safety
    net** for the orchestrator path — kept in place because:

    1. The fixture also clears AIKIDO_CLIENT_ID, which is still referenced
       (as a diagnostic in `aikidoClientIdPresent`) — without clearing,
       host env can leak into test assertions.
    2. Future scanner-related env vars added by other plugins benefit from
       the existing isolation contract.

    Tests that need to assert AIKIDO_CLIENT_ID-dependent behaviour opt in
    explicitly via `monkeypatch.setenv("AIKIDO_CLIENT_ID", ...)`.
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
