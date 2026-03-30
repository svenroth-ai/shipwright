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
        assert "No sections registered" in content

    def test_with_sections(self, project_with_sections):
        content = generate_dashboard(project_with_sections, session_id="test-456")
        assert "1/3 sections complete" in content
        assert "01-models" in content
        assert "a1b2c3d" in content
        assert "02-routes" in content
        assert "03-ui" in content

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
        assert "2/2 sections complete" in content
        assert "/shipwright-test" in content

    def test_paused_shows_resume_info(self, project_with_sections):
        content = generate_dashboard(
            project_with_sections, status="paused", session_id="test"
        )
        assert "## Resume Info" in content
        assert "/shipwright-run" in content

    def test_no_config_file(self, tmp_project):
        """No build config yet — should still generate valid dashboard."""
        content = generate_dashboard(tmp_project, session_id="test")
        assert "# Shipwright Build Dashboard" in content
        assert "No sections registered" in content


class TestStepLabels:
    def test_all_steps_have_labels(self):
        for i in range(1, 13):
            assert i in STEP_LABELS
