"""Shared test fixtures."""

import json
import shutil
import sys
from pathlib import Path

import pytest

# Add shared scripts to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))


_OSS_SCANNERS = ("semgrep", "trivy", "gitleaks")


@pytest.fixture(autouse=True)
def _isolate_scanner_environment(monkeypatch):
    """Make orchestrator._check_security_available() deterministic per host.

    Mirrors the autouse fixture in plugins/shipwright-run/tests/conftest.py
    and integration-tests/conftest.py — clears AIKIDO/SHIPWRIGHT_SCANNER_BACKEND,
    sets SHIPWRIGHT_TEST_DISABLE_OSS_SCANNERS=1 (covers subprocess invocations),
    and patches shutil.which to hide the OSS scanners from in-process callers.
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
    """Create a temporary project directory with agent_docs/."""
    agent_docs = tmp_path / "agent_docs"
    agent_docs.mkdir()
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
