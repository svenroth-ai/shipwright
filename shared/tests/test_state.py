"""Tests for state management."""

import json

from lib.state import detect_current_phase, get_checkpoint, has_handoff


def test_detect_phase_not_started(tmp_project):
    assert detect_current_phase(tmp_project) == "not_started"


def test_detect_phase_build(project_with_configs):
    """With current_step=build in run_config, returns 'build'."""
    assert detect_current_phase(project_with_configs) == "build"


def test_detect_phase_from_current_step(project_with_configs):
    """Primary path: reads current_step from run_config."""
    run_path = project_with_configs / "shipwright_run_config.json"
    config = json.loads(run_path.read_text())
    config["current_step"] = "deploy"
    run_path.write_text(json.dumps(config))

    assert detect_current_phase(project_with_configs) == "deploy"


def test_detect_phase_complete(project_with_configs):
    """All pipeline steps in completed_steps and no current_step → complete."""
    run_path = project_with_configs / "shipwright_run_config.json"
    config = json.loads(run_path.read_text())
    del config["current_step"]
    config["completed_steps"] = config["pipeline"]
    run_path.write_text(json.dumps(config))

    assert detect_current_phase(project_with_configs) == "complete"


def test_detect_phase_fallback_heuristic(tmp_project):
    """Without current_step in run_config, falls back to heuristic."""
    # Minimal run_config without current_step
    (tmp_project / "shipwright_run_config.json").write_text(
        json.dumps({"scope": "full_app"}), encoding="utf-8"
    )
    (tmp_project / "shipwright_build_config.json").write_text(
        json.dumps({"sections": [{"name": "01-x", "status": "in_progress"}]}),
        encoding="utf-8",
    )
    assert detect_current_phase(tmp_project) == "build"


def test_detect_phase_standalone_project_in_progress(tmp_project):
    """Standalone: only project_config with in_progress → returns 'project'."""
    (tmp_project / "shipwright_project_config.json").write_text(
        json.dumps({"status": "in_progress", "scope": "full_app"}), encoding="utf-8"
    )
    assert detect_current_phase(tmp_project) == "project"


def test_detect_phase_standalone_project_complete(tmp_project):
    """Standalone: project complete → returns 'design' (next step)."""
    (tmp_project / "shipwright_project_config.json").write_text(
        json.dumps({"status": "complete"}), encoding="utf-8"
    )
    assert detect_current_phase(tmp_project) == "design"


def test_detect_phase_standalone_design_in_progress(tmp_project):
    """Standalone: design in progress (flag in project_config) → returns 'design'."""
    (tmp_project / "shipwright_project_config.json").write_text(
        json.dumps({"status": "complete", "design_phase": "in_progress"}),
        encoding="utf-8",
    )
    assert detect_current_phase(tmp_project) == "design"


def test_detect_phase_standalone_design_complete(tmp_project):
    """Standalone: design complete → returns 'plan' (next step)."""
    (tmp_project / "shipwright_project_config.json").write_text(
        json.dumps({"status": "complete", "design_phase": "complete"}),
        encoding="utf-8",
    )
    assert detect_current_phase(tmp_project) == "plan"


def test_detect_phase_standalone_plan_in_progress(tmp_project):
    """Standalone: plan in progress → returns 'plan'."""
    (tmp_project / "shipwright_project_config.json").write_text(
        json.dumps({"status": "complete", "design_phase": "complete"}),
        encoding="utf-8",
    )
    (tmp_project / "shipwright_plan_config.json").write_text(
        json.dumps({"status": "in_progress"}), encoding="utf-8"
    )
    assert detect_current_phase(tmp_project) == "plan"


def test_detect_phase_standalone_plan_complete(tmp_project):
    """Standalone: plan complete → returns 'build' (next step)."""
    (tmp_project / "shipwright_plan_config.json").write_text(
        json.dumps({"status": "complete"}), encoding="utf-8"
    )
    assert detect_current_phase(tmp_project) == "build"


def test_detect_phase_stale_build_config_skipped(tmp_project):
    """Stale build config with all-complete sections is ignored."""
    (tmp_project / "shipwright_plan_config.json").write_text(
        json.dumps({"status": "in_progress"}), encoding="utf-8"
    )
    (tmp_project / "shipwright_build_config.json").write_text(
        json.dumps({"sections": [{"name": "01-x", "status": "complete"}]}),
        encoding="utf-8",
    )
    # Plan in_progress should win over stale completed build
    assert detect_current_phase(tmp_project) == "plan"


def test_get_checkpoint_empty(tmp_project):
    checkpoint = get_checkpoint(tmp_project)
    assert checkpoint["phase"] == "not_started"
    assert checkpoint["has_run_config"] is False


def test_get_checkpoint_with_data(project_with_configs):
    checkpoint = get_checkpoint(project_with_configs)
    assert checkpoint["phase"] == "build"
    assert checkpoint["has_run_config"] is True
    assert checkpoint["total_splits"] == 2
    assert checkpoint["completed_splits"] == 1
    assert checkpoint["current_split"] == "02-dashboard"
    assert checkpoint["total_sections"] == 2
    assert checkpoint["completed_sections"] == 1
    assert checkpoint["current_section"] == "02-widgets"


def test_get_checkpoint_splits_from_run_config(project_with_configs):
    """Checkpoint reads completed_splits from run_config, not project_config."""
    # Update run_config to mark both splits complete
    run_path = project_with_configs / "shipwright_run_config.json"
    config = json.loads(run_path.read_text())
    config["completed_splits"] = ["01-auth", "02-dashboard"]
    run_path.write_text(json.dumps(config))

    checkpoint = get_checkpoint(project_with_configs)
    assert checkpoint["completed_splits"] == 2
    assert checkpoint["current_split"] is None


def test_has_handoff_false(tmp_project):
    assert has_handoff(tmp_project) is False


def test_has_handoff_true(tmp_project):
    handoff = tmp_project / "agent_docs" / "session_handoff.md"
    handoff.write_text("# Handoff")
    assert has_handoff(tmp_project) is True
