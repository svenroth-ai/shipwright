"""Test fixtures for shipwright-security."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from _finalize_helpers import baseline_compliance, git_commit, git_init

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def pipeline_project(tmp_path):
    """Synthetic git repo with shipwright_project_config.json (pipeline mode)."""
    git_init(tmp_path)
    git_commit(tmp_path, baseline_compliance(), "chore: seed")
    (tmp_path / "shipwright_project_config.json").write_text(
        json.dumps({"status": "complete"}), encoding="utf-8",
    )
    (tmp_path / "shipwright_run_config.json").write_text(
        json.dumps({"status": "complete", "pipeline": []}), encoding="utf-8",
    )
    (tmp_path / ".shipwright" / "agent_docs").mkdir(parents=True, exist_ok=True)
    (tmp_path / "shipwright_events.jsonl").write_text("", encoding="utf-8")
    # Mirror the real managed .gitignore block: the append-log mutex
    # (shipwright_events.jsonl.lock / *.json.lock) is a transient runtime file
    # ignored in every pipeline-mode project. Without this, the real
    # update_compliance run in the drift-guard test would surface the lock as an
    # untracked leak the finalizer must NOT commit — the fixture would diverge
    # from production.
    (tmp_path / ".gitignore").write_text(
        "shipwright_events.jsonl.lock\n*.json.lock\n*.md.lock\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "add", "."],
                   check=True, capture_output=True)
    subprocess.run(["git", "-C", str(tmp_path), "commit", "-m", "chore: pipeline-mode setup"],
                   check=True, capture_output=True)
    return tmp_path


@pytest.fixture
def standalone_project(tmp_path):
    """Same as pipeline_project but WITHOUT shipwright_project_config.json."""
    git_init(tmp_path)
    git_commit(tmp_path, baseline_compliance(), "chore: seed")
    (tmp_path / "shipwright_run_config.json").write_text(
        json.dumps({"status": "complete", "pipeline": []}), encoding="utf-8",
    )
    (tmp_path / ".shipwright" / "agent_docs").mkdir(parents=True, exist_ok=True)
    (tmp_path / "shipwright_events.jsonl").write_text("", encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "add", "."],
                   check=True, capture_output=True)
    subprocess.run(["git", "-C", str(tmp_path), "commit", "-m", "chore: standalone-mode setup"],
                   check=True, capture_output=True)
    return tmp_path


@pytest.fixture
def sample_aikido_response() -> list[dict]:
    """Load sample Aikido API response."""
    return json.loads((FIXTURES_DIR / "sample_aikido_response.json").read_text())


@pytest.fixture
def sample_fixable_findings() -> dict:
    """Load sample findings with expected classifications."""
    return json.loads((FIXTURES_DIR / "sample_fixable_findings.json").read_text())


@pytest.fixture
def sample_semgrep_output() -> dict:
    """Load sample Semgrep JSON output."""
    return json.loads((FIXTURES_DIR / "sample_semgrep_output.json").read_text())


@pytest.fixture
def sample_trivy_output() -> dict:
    """Load sample Trivy JSON output."""
    return json.loads((FIXTURES_DIR / "sample_trivy_output.json").read_text())


@pytest.fixture
def sample_gitleaks_output() -> list:
    """Load sample Gitleaks JSON output."""
    return json.loads((FIXTURES_DIR / "sample_gitleaks_output.json").read_text())
