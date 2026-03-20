"""Tests for state management."""

from lib.state import detect_current_phase, get_checkpoint, has_handoff


def test_detect_phase_not_started(tmp_project):
    assert detect_current_phase(tmp_project) == "not_started"


def test_detect_phase_build(project_with_configs):
    assert detect_current_phase(project_with_configs) == "build"


def test_detect_phase_complete(project_with_configs):
    import json

    # Mark build as complete
    build_path = project_with_configs / "shipwright_build_config.json"
    config = json.loads(build_path.read_text())
    config["status"] = "complete"
    build_path.write_text(json.dumps(config))

    assert detect_current_phase(project_with_configs) == "complete"


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


def test_has_handoff_false(tmp_project):
    assert has_handoff(tmp_project) is False


def test_has_handoff_true(tmp_project):
    handoff = tmp_project / "agent_docs" / "session_handoff.md"
    handoff.write_text("# Handoff")
    assert has_handoff(tmp_project) is True
