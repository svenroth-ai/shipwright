"""Tests for get_phase_context.py — the phase skills' invocation-mode authority.

Three outcomes, never two: `standalone` ONLY when no dispatch token is supplied (carrying
the live-run snapshot), `pipeline` for a valid actionable token, and `error` when a token
WAS supplied but is unresolvable / stale / terminal / wrong-phase — which must never
degrade to standalone (see shared/scripts/lib/phase_invocation_mode.py). Plus split-aware
artifact suggestions and a drift pin on TERMINAL_STATUSES.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO / "shared" / "scripts" / "tools"))
sys.path.insert(0, str(_REPO / "shared" / "scripts" / "lib"))
sys.path.insert(0, str(_REPO / "plugins" / "shipwright-run" / "scripts" / "lib"))

import phase_task_lifecycle as ptl  # noqa: E402
from get_phase_context import build_phase_context  # noqa: E402
from orchestrator import create_config  # noqa: E402
from phase_invocation_mode import TERMINAL_STATUSES  # noqa: E402


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


def _read_cfg(project_root):
    return json.loads((project_root / "shipwright_run_config.json").read_text("utf-8"))


def _write_cfg(project_root, cfg):
    (project_root / "shipwright_run_config.json").write_text(
        json.dumps(cfg), encoding="utf-8",
    )


def _project_task(project_root):
    return _read_cfg(project_root)["phase_tasks"][0]


def _claim(project_root, task):
    """Claim exactly as the orchestrator does before it dispatches the phase-runner."""
    return ptl.claim_phase_task(
        project_root,
        phase_task_id=task["phaseTaskId"],
        session_uuid=task["sessionUuid"],
        expected_phase=task["phase"],
    )


# ---- Standalone: no token supplied (the ONLY standalone trigger) ----


def test_no_phase_task_id_on_idle_project_is_standalone(tmp_path):
    out = build_phase_context(tmp_path, None)
    assert out["mode"] == "standalone"
    assert out["reason"] == "no_phase_task_id"
    assert out["pipeline_active"] is False
    assert out["active_phases"] == []
    assert out["requires_out_of_sequence_warning"] is False


def test_no_phase_task_id_while_a_driven_run_is_live_warns_out_of_sequence(v2_project):
    """Hand-invoking a phase skill while the orchestrator is driving a run is out-of-band.

    The warning is pre-computed as a boolean so the skill does a binary check instead of
    intersecting active_phases against its own phase in prose.
    """
    _claim(v2_project, _project_task(v2_project))

    out = build_phase_context(v2_project, None)
    assert out["mode"] == "standalone"
    assert out["pipeline_active"] is True
    assert out["active_phases"] == ["project"]
    assert out["requires_out_of_sequence_warning"] is True


def test_completed_run_is_not_live(v2_project):
    cfg = _read_cfg(v2_project)
    cfg["status"] = "complete"
    for task in cfg["phase_tasks"]:
        task["status"] = "done"
    _write_cfg(v2_project, cfg)

    out = build_phase_context(v2_project, None)
    assert out["mode"] == "standalone"
    assert out["pipeline_active"] is False
    assert out["requires_out_of_sequence_warning"] is False


def test_in_progress_run_with_only_terminal_tasks_is_not_live(v2_project):
    """status alone does not make a run live — a non-terminal phase_task must exist."""
    cfg = _read_cfg(v2_project)
    cfg["status"] = "in_progress"
    for task in cfg["phase_tasks"]:
        task["status"] = "done"
    _write_cfg(v2_project, cfg)

    out = build_phase_context(v2_project, None)
    assert out["pipeline_active"] is False
    assert out["active_phases"] == []


def test_active_phases_dedupes_concurrent_split_tasks(v2_project):
    """A fanned-out build has several concurrent tasks on the SAME phase.

    This is the frontier shape a scalar `current_step` can never represent — the
    load-bearing reason the v1 fields were not simply revived.
    """
    cfg = _read_cfg(v2_project)
    cfg["phase_tasks"][0]["status"] = "done"
    for split in ("01-core", "02-ui"):
        cfg["phase_tasks"].append({
            "phaseTaskId": f"ptk-build-{split}", "phase": "build", "splitId": split,
            "sessionUuid": f"su-{split}", "version": 1, "status": "in_progress",
            "title": f"build / {split}", "slashCommand": "/shipwright-build",
            "prerequisites": [], "claimedBySessionUuid": f"su-{split}",
            "claimAttemptedAt": "z", "executionCount": 1, "createdAt": "z",
            "awaitingLaunchAt": "z", "startedAt": "z", "completedAt": None,
            "result": None, "errors": [],
        })
    _write_cfg(v2_project, cfg)

    out = build_phase_context(v2_project, None)
    assert out["pipeline_active"] is True
    assert out["active_phases"] == ["build"]  # deduped, not ["build", "build"]


# ---- Error: a token WAS supplied but does not resolve (never standalone) ----


def test_token_with_no_run_config_is_error_not_standalone(tmp_path):
    """The regression this iterate exists to prevent: a dispatched phase must never
    silently degrade to standalone just because the config could not be read."""
    out = build_phase_context(tmp_path, "ptk-anything")
    assert out["mode"] == "error"
    assert out["reason"] == "no_run_config"
    assert "ptk-anything" in out["message"]


def test_token_with_v1_config_is_error(tmp_path):
    project = tmp_path / "v1"
    project.mkdir()
    (project / "shipwright_run_config.json").write_text(
        json.dumps({"current_step": "project"}), encoding="utf-8",
    )
    out = build_phase_context(project, "ptk-x")
    assert out["mode"] == "error"
    assert out["reason"] == "run_config_unreadable"


def test_token_with_corrupt_run_config_is_error(tmp_path):
    project = tmp_path / "corrupt"
    project.mkdir()
    (project / "shipwright_run_config.json").write_text("{not json", encoding="utf-8")
    out = build_phase_context(project, "ptk-x")
    assert out["mode"] == "error"
    assert out["reason"] == "run_config_unreadable"


def test_unknown_token_is_error(v2_project):
    out = build_phase_context(v2_project, "ptk-nonexistent")
    assert out["mode"] == "error"
    assert out["reason"] == "phase_task_id_not_found"


def test_token_for_another_phase_is_error(v2_project):
    """A stale or hand-copied id must not grant pipeline authority over someone
    else's task."""
    task = _project_task(v2_project)
    _claim(v2_project, task)

    out = build_phase_context(v2_project, task["phaseTaskId"], phase="build")
    assert out["mode"] == "error"
    assert out["reason"] == "wrong_phase_for_phase_task"


def test_terminal_token_is_error(v2_project):
    """A replayed token from an already-completed phase must not re-enter pipeline mode."""
    task = _project_task(v2_project)
    _claim(v2_project, task)
    fresh = _project_task(v2_project)
    ptl.complete_phase_task(
        v2_project, phase_task_id=fresh["phaseTaskId"],
        session_uuid=fresh["sessionUuid"], expected_version=fresh["version"],
        result={"ok": True, "phase": "project", "summary": "s", "artifacts": []},
    )

    out = build_phase_context(v2_project, fresh["phaseTaskId"], phase="project")
    assert out["mode"] == "error"
    assert out["reason"] == "phase_task_not_actionable"


def test_unclaimed_token_is_error(v2_project):
    """The orchestrator claims a task BEFORE dispatching it, so an awaiting_launch task
    means nobody actually dispatched this invocation."""
    task = _project_task(v2_project)
    assert task["status"] == "awaiting_launch"

    out = build_phase_context(v2_project, task["phaseTaskId"], phase="project")
    assert out["mode"] == "error"
    assert out["reason"] == "phase_task_not_actionable"


# ---- Pipeline mode ----


def test_pipeline_mode_for_dispatched_project_task(v2_project):
    task = _project_task(v2_project)
    _claim(v2_project, task)

    out = build_phase_context(v2_project, task["phaseTaskId"], phase="project")
    assert out["mode"] == "pipeline"
    assert out["phaseTaskId"] == task["phaseTaskId"]
    assert out["phase"] == "project"
    assert out["splitId"] is None
    assert out["version"] == 1
    assert out["slashCommand"] == "/shipwright-project"
    assert out["prerequisites"] == []  # initial task has none
    assert out["runConditions"]["securityEnabled"] is False
    assert out["splits_frozen"] == []
    assert isinstance(out["skill_artifacts_to_read"], list)
    assert "next_action_hint" in out


def test_pipeline_mode_without_declared_phase_still_resolves(v2_project):
    """--phase is optional; omitting it skips only the wrong-phase check."""
    task = _project_task(v2_project)
    _claim(v2_project, task)

    out = build_phase_context(v2_project, task["phaseTaskId"])
    assert out["mode"] == "pipeline"


def test_pipeline_mode_resolves_prerequisites(v2_project):
    project_task = _project_task(v2_project)
    cfg = _read_cfg(v2_project)
    cfg["phase_tasks"][0]["status"] = "done"
    cfg["phase_tasks"].append({
        "phaseTaskId": "ptk-design", "phase": "design", "splitId": None,
        "sessionUuid": "x", "version": 1, "status": "in_progress",
        "title": "design", "slashCommand": "/shipwright-design",
        "prerequisites": [project_task["phaseTaskId"]],
        "claimedBySessionUuid": "x", "claimAttemptedAt": "z",
        "executionCount": 1, "createdAt": "z", "awaitingLaunchAt": "z",
        "startedAt": "z", "completedAt": None, "result": None, "errors": [],
    })
    _write_cfg(v2_project, cfg)

    out = build_phase_context(v2_project, "ptk-design", phase="design")
    assert out["mode"] == "pipeline"
    assert len(out["prerequisites"]) == 1
    pred = out["prerequisites"][0]
    assert pred["phaseTaskId"] == project_task["phaseTaskId"]
    assert pred["status"] == "done"
    assert ".shipwright/planning/requirements.md" in pred["artifacts"]
    assert any("requirements" in p for p in out["skill_artifacts_to_read"])


def test_pipeline_build_split_uses_split_scoped_paths(v2_project):
    cfg = _read_cfg(v2_project)
    cfg["phase_tasks"].append({
        "phaseTaskId": "ptk-build-01", "phase": "build", "splitId": "01-core",
        "sessionUuid": "y", "version": 1, "status": "in_progress",
        "title": "build / 01-core", "slashCommand": "/shipwright-build",
        "prerequisites": [], "claimedBySessionUuid": "y",
        "claimAttemptedAt": "z", "executionCount": 1, "createdAt": "z",
        "awaitingLaunchAt": "z", "startedAt": "z", "completedAt": None,
        "result": None, "errors": [],
    })
    _write_cfg(v2_project, cfg)

    out = build_phase_context(v2_project, "ptk-build-01", phase="build")
    assert out["splitId"] == "01-core"
    assert ".shipwright/agent_docs/sections/01-core/" in out["skill_artifacts_to_read"]
    assert ".shipwright/agent_docs/sections/" not in out["skill_artifacts_to_read"]


# ---- Drift protection ----


def test_terminal_statuses_sync():
    """The resolver keeps a self-contained copy of the lifecycle's terminal statuses (it
    must not hard-import the run plugin — see ADR-044). Pin it to the SSoT, both
    directions, so a lifecycle change cannot silently desync the invocation-mode gate."""
    assert TERMINAL_STATUSES == ptl.TERMINAL_STATUSES
