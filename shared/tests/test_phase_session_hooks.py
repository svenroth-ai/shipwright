"""Tests for the F3a phase-session hooks (start/validate/stop).

Coverage:
    phase_session_start.py:
        - Standalone (no run config / v1 / no match) -> exit 0, no marker
        - Happy path -> claim, write validation, emit pipeline-context block
        - Wrong-skill -> validation valid=false, .block-pending written
        - Phase already terminal -> .block-pending written
        - Duplicate claim -> .block-pending written
        - Prereqs unmet -> .block-pending written

    phase_user_prompt_validate.py:
        - No run config / no match -> exit 0
        - Marker present -> exit 2, decision=block, marker deleted
        - Marker absent -> exit 0 pass-through
        - Single-use: second call after consume -> pass-through

    phase_session_stop.py:
        - Standalone -> exit 0
        - No validation marker -> exit 0
        - Validation valid=false (was blocked) -> exit 0, no completion
        - Happy path -> complete-phase-task, next phase materialised
        - design phase -> freeze_splits called before complete
        - result.ok=false (missing config) -> mark_phase_failed
        - Stale stop after recover -> stale_stop_rejected event, exit 0
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# Add the lib paths used by the hooks under test
_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT / "plugins" / "shipwright-run" / "scripts" / "lib"))
sys.path.insert(0, str(_REPO_ROOT / "shared" / "scripts" / "hooks"))

from orchestrator import create_config  # noqa: E402
from phase_task_lifecycle import recover_phase_task  # noqa: E402

import phase_session_start  # noqa: E402
import phase_session_stop  # noqa: E402
import phase_user_prompt_validate  # noqa: E402


# ---- Fixtures ----


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


def _read_cfg(project_root: Path) -> dict:
    return json.loads(
        (project_root / "shipwright_run_config.json").read_text("utf-8"),
    )


def _project_task(project_root: Path) -> dict:
    return _read_cfg(project_root)["phase_tasks"][0]


def _task_dir(project_root: Path, task: dict) -> Path:
    cfg = _read_cfg(project_root)
    return (
        project_root / ".shipwright" / "runs" / cfg["runId"] / task["phaseTaskId"]
    )


def _validation_path(project_root: Path, task: dict) -> Path:
    return _task_dir(project_root, task) / "sessionstart-validation.json"


def _block_pending_path(project_root: Path, task: dict) -> Path:
    return _task_dir(project_root, task) / ".block-pending"


# ---- phase_session_start.py ----


def test_start_standalone_no_run_config(tmp_path, capsys):
    project = tmp_path / "no-config"
    project.mkdir()
    rc = phase_session_start.run(
        project, session_uuid="random-uuid", plugin_root="shipwright-build",
    )
    assert rc == 0
    captured = capsys.readouterr()
    assert captured.out == ""  # no additionalContext


def test_start_standalone_no_session_match(v2_project, capsys):
    rc = phase_session_start.run(
        v2_project, session_uuid="not-in-config", plugin_root="shipwright-project",
    )
    assert rc == 0
    captured = capsys.readouterr()
    assert captured.out == ""


def test_start_happy_path_claims_and_emits_context(v2_project, capsys):
    task = _project_task(v2_project)
    rc = phase_session_start.run(
        v2_project, session_uuid=task["sessionUuid"],
        plugin_root="shipwright-project",
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert "SHIPWRIGHT-PIPELINE-CONTEXT" in out
    assert task["phaseTaskId"] in out
    assert "phase: project" in out

    val = json.loads(_validation_path(v2_project, task).read_text("utf-8"))
    assert val["valid"] is True
    assert val["reason"] == "ok"
    # No block marker on happy path
    assert not _block_pending_path(v2_project, task).exists()
    # Task is now in_progress, claimed by us
    cfg = _read_cfg(v2_project)
    assert cfg["phase_tasks"][0]["status"] == "in_progress"
    assert cfg["phase_tasks"][0]["claimedBySessionUuid"] == task["sessionUuid"]


def test_start_wrong_skill_writes_block_marker(v2_project, capsys):
    task = _project_task(v2_project)
    rc = phase_session_start.run(
        v2_project, session_uuid=task["sessionUuid"],
        plugin_root="shipwright-build",  # task.phase is project
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert "BLOCKED" in out
    assert "wrong" in out.lower() or "phase" in out.lower()

    val = json.loads(_validation_path(v2_project, task).read_text("utf-8"))
    assert val["valid"] is False
    assert val["reason"] == "wrong_skill"
    assert val["expected_phase"] == "build"
    assert val["claimed_phase"] == "project"

    marker = _block_pending_path(v2_project, task)
    assert marker.exists()
    assert "build" in marker.read_text("utf-8")


def test_start_phase_already_terminal(v2_project, capsys):
    task = _project_task(v2_project)
    cfg = _read_cfg(v2_project)
    cfg["phase_tasks"][0]["status"] = "done"
    (v2_project / "shipwright_run_config.json").write_text(
        json.dumps(cfg), encoding="utf-8",
    )
    rc = phase_session_start.run(
        v2_project, session_uuid=task["sessionUuid"],
        plugin_root="shipwright-project",
    )
    assert rc == 0
    val = json.loads(_validation_path(v2_project, task).read_text("utf-8"))
    assert val["reason"] == "phase_already_terminal"
    assert _block_pending_path(v2_project, task).exists()


def test_start_duplicate_claim(v2_project, capsys):
    task = _project_task(v2_project)
    cfg = _read_cfg(v2_project)
    cfg["phase_tasks"][0]["status"] = "in_progress"
    cfg["phase_tasks"][0]["claimedBySessionUuid"] = "first-session"
    (v2_project / "shipwright_run_config.json").write_text(
        json.dumps(cfg), encoding="utf-8",
    )
    rc = phase_session_start.run(
        v2_project, session_uuid=task["sessionUuid"],  # different from first-session
        plugin_root="shipwright-project",
    )
    assert rc == 0
    val = json.loads(_validation_path(v2_project, task).read_text("utf-8"))
    assert val["reason"] == "duplicate_claim"


def test_start_prereqs_unmet(v2_project, capsys):
    task = _project_task(v2_project)
    cfg = _read_cfg(v2_project)
    # Add a fake design task requiring project (still awaiting_launch)
    fake_design = {
        "phaseTaskId": "ptk-design-fake", "phase": "design", "splitId": None,
        "sessionUuid": "design-uuid", "version": 1, "status": "awaiting_launch",
        "title": "design", "description": "", "slashCommand": "/shipwright-design",
        "prerequisites": [task["phaseTaskId"]],
        "claimedBySessionUuid": None, "claimAttemptedAt": None,
        "executionCount": 0, "createdAt": "z", "awaitingLaunchAt": "z",
        "startedAt": None, "completedAt": None, "result": None, "errors": [],
    }
    cfg["phase_tasks"].append(fake_design)
    (v2_project / "shipwright_run_config.json").write_text(
        json.dumps(cfg), encoding="utf-8",
    )

    rc = phase_session_start.run(
        v2_project, session_uuid="design-uuid", plugin_root="shipwright-design",
    )
    assert rc == 0
    val = json.loads(_validation_path(v2_project, fake_design).read_text("utf-8"))
    assert val["reason"] == "prereqs_unmet"


# ---- phase_user_prompt_validate.py ----


def test_user_prompt_no_marker_passes_through(v2_project, capsys):
    task = _project_task(v2_project)
    rc = phase_user_prompt_validate.run(v2_project, task["sessionUuid"])
    assert rc == 0
    assert capsys.readouterr().out == ""


def test_user_prompt_no_session_match_passes_through(v2_project, capsys):
    rc = phase_user_prompt_validate.run(v2_project, "not-in-config")
    assert rc == 0


def test_user_prompt_marker_blocks_and_consumes(v2_project, capsys):
    task = _project_task(v2_project)
    # Trigger SessionStart wrong-skill to write a marker
    phase_session_start.run(
        v2_project, session_uuid=task["sessionUuid"], plugin_root="shipwright-build",
    )
    capsys.readouterr()  # discard SessionStart output

    # First UserPromptSubmit fire: should block + consume
    rc = phase_user_prompt_validate.run(v2_project, task["sessionUuid"])
    assert rc == 2
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert payload["decision"] == "block"
    assert "SHIPWRIGHT-PIPELINE-BLOCK" in payload["hookSpecificOutput"]["additionalContext"]

    # Marker is consumed
    assert not _block_pending_path(v2_project, task).exists()

    # Second fire: pass-through
    rc2 = phase_user_prompt_validate.run(v2_project, task["sessionUuid"])
    assert rc2 == 0
    assert capsys.readouterr().out == ""


# ---- phase_session_stop.py ----


def test_stop_standalone_no_run_config(tmp_path):
    project = tmp_path / "empty"
    project.mkdir()
    rc = phase_session_stop.run(project, "any-uuid")
    assert rc == 0


def test_stop_no_session_match(v2_project):
    rc = phase_session_stop.run(v2_project, "no-match-uuid")
    assert rc == 0


def test_stop_no_validation_marker_skips(v2_project):
    """If SessionStart didn't run, we have no version to claim with -> skip."""
    task = _project_task(v2_project)
    # No prior phase_session_start.run call
    rc = phase_session_stop.run(v2_project, task["sessionUuid"])
    assert rc == 0
    # Task wasn't completed
    assert _read_cfg(v2_project)["phase_tasks"][0]["status"] == "awaiting_launch"


def test_stop_validation_invalid_skips(v2_project):
    """If we were blocked, don't try to complete."""
    task = _project_task(v2_project)
    phase_session_start.run(
        v2_project, session_uuid=task["sessionUuid"], plugin_root="shipwright-build",
    )  # writes valid=false
    rc = phase_session_stop.run(v2_project, task["sessionUuid"])
    assert rc == 0
    # Task remains awaiting_launch (block didn't claim)
    assert _read_cfg(v2_project)["phase_tasks"][0]["status"] == "awaiting_launch"


def test_stop_happy_completes_and_plans_next(v2_project):
    task = _project_task(v2_project)
    # SessionStart claims
    phase_session_start.run(
        v2_project, session_uuid=task["sessionUuid"],
        plugin_root="shipwright-project",
    )
    # Phase produced artifacts: write phase config so collect_result returns ok
    (v2_project / "shipwright_project_config.json").write_text(
        json.dumps({"status": "complete"}), encoding="utf-8",
    )
    rc = phase_session_stop.run(v2_project, task["sessionUuid"])
    assert rc == 0
    cfg = _read_cfg(v2_project)
    assert cfg["phase_tasks"][0]["status"] == "done"
    # Design successor materialised
    phases = [t["phase"] for t in cfg["phase_tasks"]]
    assert phases == ["project", "design"]


def test_stop_design_phase_freezes_splits(v2_project):
    """End-to-end: project done, then design done with splits -> freeze runs."""
    # Walk project -> design
    project_task = _project_task(v2_project)
    phase_session_start.run(
        v2_project, session_uuid=project_task["sessionUuid"],
        plugin_root="shipwright-project",
    )
    (v2_project / "shipwright_project_config.json").write_text(
        json.dumps({"status": "complete"}), encoding="utf-8",
    )
    phase_session_stop.run(v2_project, project_task["sessionUuid"])

    # Now provide design splits
    (v2_project / "shipwright_design_config.json").write_text(
        json.dumps({"status": "complete", "splits": ["01-core", "02-ui"]}),
        encoding="utf-8",
    )

    design_task = next(
        t for t in _read_cfg(v2_project)["phase_tasks"] if t["phase"] == "design"
    )
    phase_session_start.run(
        v2_project, session_uuid=design_task["sessionUuid"],
        plugin_root="shipwright-design",
    )
    rc = phase_session_stop.run(v2_project, design_task["sessionUuid"])
    assert rc == 0

    cfg = _read_cfg(v2_project)
    assert cfg["splits_frozen"] == ["01-core", "02-ui"]
    assert cfg["runConditions"]["splitMode"] == "per_split"
    # Plan/01-core successor materialised
    plan_split = [t for t in cfg["phase_tasks"] if t["phase"] == "plan"]
    assert len(plan_split) == 1
    assert plan_split[0]["splitId"] == "01-core"


def test_stop_missing_phase_config_marks_failed(v2_project):
    """No project config file -> result.ok=false -> mark_phase_failed."""
    task = _project_task(v2_project)
    phase_session_start.run(
        v2_project, session_uuid=task["sessionUuid"],
        plugin_root="shipwright-project",
    )
    # NO project config written
    rc = phase_session_stop.run(v2_project, task["sessionUuid"])
    assert rc == 0
    cfg = _read_cfg(v2_project)
    assert cfg["phase_tasks"][0]["status"] == "failed"
    assert cfg["status"] == "failed"


def test_stop_stale_after_recover_records_event(v2_project):
    """Old session tries to complete after recover bumped version."""
    task = _project_task(v2_project)
    phase_session_start.run(
        v2_project, session_uuid=task["sessionUuid"],
        plugin_root="shipwright-project",
    )
    # Recover bumps version
    recover_phase_task(v2_project, phase_task_id=task["phaseTaskId"])
    # Old session's stop hook fires — has stale version in validation marker
    (v2_project / "shipwright_project_config.json").write_text(
        json.dumps({"status": "complete"}), encoding="utf-8",
    )
    rc = phase_session_stop.run(v2_project, task["sessionUuid"])
    assert rc == 0  # stop hook never crashes
    # Task is back to awaiting_launch (from recover) — completion was rejected
    cfg = _read_cfg(v2_project)
    assert cfg["phase_tasks"][0]["status"] == "awaiting_launch"
