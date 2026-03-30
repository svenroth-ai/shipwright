"""Tests for update_build_dashboard.py."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.update_build_dashboard import generate_dashboard, format_status, STEP_LABELS


@pytest.fixture
def tmp_project(tmp_path):
    (tmp_path / "agent_docs").mkdir()
    return tmp_path


@pytest.fixture
def project_with_sections(tmp_project):
    """Project with 3 sections in various states."""
    config = {
        "sections": [
            {"name": "01-models", "status": "complete", "commit": "a1b2c3d"},
            {"name": "02-routes", "status": "in_progress"},
            {"name": "03-ui", "status": "pending"},
        ]
    }
    (tmp_project / "shipwright_build_config.json").write_text(
        json.dumps(config, indent=2), encoding="utf-8"
    )
    return tmp_project


@pytest.fixture
def project_with_pipeline(tmp_project):
    """Project with run config (pipeline status)."""
    run_config = {
        "pipeline": ["project", "design", "plan", "build", "test", "deploy", "changelog"],
        "completed_steps": ["project", "design", "plan"],
        "current_step": "build",
    }
    build_config = {
        "sections": [
            {"name": "01-auth", "status": "complete", "commit": "abc"},
            {"name": "02-api", "status": "in_progress"},
            {"name": "03-ui", "status": "pending"},
        ]
    }
    (tmp_project / "shipwright_run_config.json").write_text(
        json.dumps(run_config), encoding="utf-8"
    )
    (tmp_project / "shipwright_build_config.json").write_text(
        json.dumps(build_config), encoding="utf-8"
    )
    return tmp_project


class TestFormatStatus:
    def test_complete(self):
        sec = {"name": "01-auth", "status": "complete"}
        assert format_status(sec, None, None, None) == "complete"

    def test_pending(self):
        sec = {"name": "03-ui", "status": "pending"}
        assert format_status(sec, None, None, None) == "pending"

    def test_current_section_with_step(self):
        sec = {"name": "02-api", "status": "in_progress"}
        result = format_status(sec, "02-api", 4, None)
        assert "step 4/12" in result
        assert "Implement" in result
        assert result.startswith("**")

    def test_failed(self):
        sec = {"name": "01-auth", "status": "failed"}
        assert format_status(sec, None, None, None) == "FAILED"

    def test_paused(self):
        sec = {"name": "01-auth", "status": "paused"}
        assert format_status(sec, None, None, None) == "paused"


class TestGenerateDashboard:
    def test_empty_state(self, tmp_project):
        content = generate_dashboard(tmp_project, session_id="test-123")
        assert "# Shipwright Build Dashboard" in content
        assert "test-123" in content

    def test_with_sections(self, project_with_sections):
        content = generate_dashboard(project_with_sections, session_id="test-456")
        assert "1/3" in content
        assert "01-models" in content
        assert "a1b2c3d" in content

    def test_current_activity(self, project_with_sections):
        content = generate_dashboard(
            project_with_sections,
            section="02-routes",
            step=4,
            detail="8/12 tests passing",
            session_id="test-789",
        )
        assert "## Current Activity" in content
        assert "02-routes" in content
        assert "Implement" in content
        assert "8/12 tests passing" in content

    def test_all_complete(self, tmp_project):
        config = {
            "sections": [
                {"name": "01-auth", "status": "complete", "commit": "abc"},
                {"name": "02-api", "status": "complete", "commit": "def"},
            ]
        }
        (tmp_project / "shipwright_build_config.json").write_text(
            json.dumps(config), encoding="utf-8"
        )
        content = generate_dashboard(tmp_project, session_id="test")
        assert "2/2" in content
        assert "/shipwright-test" in content

    def test_paused_shows_resume_info(self, project_with_sections):
        content = generate_dashboard(
            project_with_sections, status="paused", session_id="test"
        )
        assert "## Resume Info" in content
        assert "/shipwright-run" in content

    def test_no_config_file(self, tmp_project):
        content = generate_dashboard(tmp_project, session_id="test")
        assert "# Shipwright Build Dashboard" in content


class TestPipelineTable:
    def test_pipeline_shown_when_run_config_exists(self, project_with_pipeline):
        content = generate_dashboard(project_with_pipeline, session_id="test")
        assert "## Pipeline" in content
        assert "| Project | complete |" in content
        assert "| Design | complete |" in content
        assert "| Plan | complete |" in content
        assert "1/3 sections" in content  # Build shows section progress

    def test_pipeline_not_shown_without_run_config(self, tmp_project):
        content = generate_dashboard(tmp_project, session_id="test")
        assert "## Pipeline" not in content

    def test_pipeline_pending_phases(self, project_with_pipeline):
        content = generate_dashboard(project_with_pipeline, session_id="test")
        assert "| Test | pending |" in content
        assert "| Deploy | pending |" in content

    def test_pipeline_with_phase_param(self, project_with_pipeline):
        content = generate_dashboard(
            project_with_pipeline, phase="build", session_id="test"
        )
        assert "## Pipeline" in content


class TestStepLabels:
    def test_all_steps_have_labels(self):
        for i in range(1, 13):
            assert i in STEP_LABELS
