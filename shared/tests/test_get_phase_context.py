"""Tests for get_phase_context.py — Phase Skill Step 0 tool.

Coverage:
    - Standalone payloads: no phase-task-id, no run config, v1 config,
      phase task not found.
    - Pipeline mode: full payload incl. prerequisites and artifact suggestions.
    - Split-aware artifact suggestions for build/<split>.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO / "shared" / "scripts" / "tools"))
sys.path.insert(0, str(_REPO / "plugins" / "shipwright-run" / "scripts" / "lib"))

from get_phase_context import build_phase_context  # noqa: E402
from orchestrator import create_config  # noqa: E402


@pytest.fixture
def v2_project(tmp_path, monkeypatch):
    monkeypatch.delenv("AIKIDO_CLIENT_ID", raising=False)
    project = tmp_path / "proj"
    project.mkdir()
    create_config(
        scope="full_app", profile="supabase-nextjs",
        autonomy="guided", deploy_target="jelastic-dev",
        project_root=project,
    )
    return project


def _project_task(project_root):
    cfg = json.loads((project_root / "shipwright_run_config.json").read_text("utf-8"))
    return cfg["phase_tasks"][0]


# ---- Standalone payloads ----


def test_no_phase_task_id_returns_standalone(v2_project):
    out = build_phase_context(v2_project, None)
    assert out["mode"] == "standalone"
    assert out["reason"] == "no_phase_task_id"


def test_no_run_config_returns_standalone(tmp_path):
    out = build_phase_context(tmp_path, "ptk-anything")
    assert out["mode"] == "standalone"
    assert out["reason"] == "no_run_config"


def test_v1_config_returns_standalone(tmp_path):
    project = tmp_path / "v1"
    project.mkdir()
    (project / "shipwright_run_config.json").write_text(
        json.dumps({"current_step": "project"}), encoding="utf-8",
    )
    out = build_phase_context(project, "ptk-x")
    assert out["mode"] == "standalone"
    assert out["reason"] == "schema_v1_legacy"


def test_phase_task_id_not_found_returns_standalone(v2_project):
    out = build_phase_context(v2_project, "ptk-nonexistent")
    assert out["mode"] == "standalone"
    assert out["reason"] == "phase_task_id_not_found"


# ---- Pipeline mode ----


def test_pipeline_mode_for_initial_project_task(v2_project):
    task = _project_task(v2_project)
    out = build_phase_context(v2_project, task["phaseTaskId"])
    assert out["mode"] == "pipeline"
    assert out["phaseTaskId"] == task["phaseTaskId"]
    assert out["phase"] == "project"
    assert out["splitId"] is None
    assert out["version"] == 1
    assert out["slashCommand"] == "/shipwright-project"
    assert out["prerequisites"] == []  # initial task has none
    assert "runConditions" in out
    assert out["runConditions"]["securityEnabled"] is False
    assert out["splits_frozen"] == []
    assert isinstance(out["skill_artifacts_to_read"], list)
    assert "next_action_hint" in out


def test_pipeline_mode_resolves_prerequisites(v2_project):
    """Inject a successor task and verify its prereq is rendered with the
    predecessor's status + artifact list."""
    project_task = _project_task(v2_project)
    cfg = json.loads(
        (v2_project / "shipwright_run_config.json").read_text("utf-8"),
    )
    cfg["phase_tasks"][0]["status"] = "done"
    cfg["phase_tasks"].append({
        "phaseTaskId": "ptk-design", "phase": "design", "splitId": None,
        "sessionUuid": "x", "version": 1, "status": "awaiting_launch",
        "title": "design", "slashCommand": "/shipwright-design",
        "prerequisites": [project_task["phaseTaskId"]],
        "claimedBySessionUuid": None, "claimAttemptedAt": None,
        "executionCount": 0, "createdAt": "z", "awaitingLaunchAt": "z",
        "startedAt": None, "completedAt": None, "result": None, "errors": [],
    })
    (v2_project / "shipwright_run_config.json").write_text(
        json.dumps(cfg), encoding="utf-8",
    )
    out = build_phase_context(v2_project, "ptk-design")
    assert out["mode"] == "pipeline"
    assert len(out["prerequisites"]) == 1
    pred = out["prerequisites"][0]
    assert pred["phaseTaskId"] == project_task["phaseTaskId"]
    assert pred["status"] == "done"
    assert "planning/requirements.md" in pred["artifacts"]
    # design-phase artifact suggestions include project artifacts as prereqs
    assert any("requirements" in p for p in out["skill_artifacts_to_read"])


def test_pipeline_build_split_uses_split_scoped_paths(v2_project):
    cfg = json.loads(
        (v2_project / "shipwright_run_config.json").read_text("utf-8"),
    )
    cfg["phase_tasks"].append({
        "phaseTaskId": "ptk-build-01", "phase": "build", "splitId": "01-core",
        "sessionUuid": "y", "version": 1, "status": "awaiting_launch",
        "title": "build / 01-core", "slashCommand": "/shipwright-build",
        "prerequisites": [], "claimedBySessionUuid": None,
        "claimAttemptedAt": None, "executionCount": 0, "createdAt": "z",
        "awaitingLaunchAt": "z", "startedAt": None, "completedAt": None,
        "result": None, "errors": [],
    })
    (v2_project / "shipwright_run_config.json").write_text(
        json.dumps(cfg), encoding="utf-8",
    )
    out = build_phase_context(v2_project, "ptk-build-01")
    assert out["splitId"] == "01-core"
    # Split-scoped sections dir replaces the generic one
    assert "agent_docs/sections/01-core/" in out["skill_artifacts_to_read"]
    assert "agent_docs/sections/" not in out["skill_artifacts_to_read"]


def test_corrupt_run_config_returns_standalone(tmp_path):
    project = tmp_path / "corrupt"
    project.mkdir()
    (project / "shipwright_run_config.json").write_text("{not json", encoding="utf-8")
    out = build_phase_context(project, "ptk-x")
    assert out["mode"] == "standalone"
    assert out["reason"] == "run_config_parse_error"
