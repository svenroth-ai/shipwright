"""Integration test: Build autopilot flow.

Simulates the full autopilot lifecycle:
  1. Init config with sections
  2. Complete sections one by one
  3. Verify dashboard updates
  4. Simulate context pressure → checkpoint
  5. Resume detection after checkpoint
  6. All sections complete → verify final state
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import SHARED_SCRIPTS, run_shared_script

# Plugin paths
REPO_ROOT = Path(__file__).resolve().parent.parent
RUN_PLUGIN = REPO_ROOT / "plugins" / "shipwright-run"
BUILD_PLUGIN = REPO_ROOT / "plugins" / "shipwright-build"

ORCHESTRATOR = str(RUN_PLUGIN / "scripts" / "lib" / "orchestrator.py")
DASHBOARD = str(SHARED_SCRIPTS / "tools" / "update_build_dashboard.py")
PRESSURE = str(SHARED_SCRIPTS / "tools" / "estimate_context_pressure.py")
UPDATE_STATE = str(BUILD_PLUGIN / "scripts" / "tools" / "update_section_state.py")


def run_script_json(script: str, args: list[str]) -> dict:
    """Run a Python script and parse JSON output."""
    result = subprocess.run(
        [sys.executable, script] + args,
        capture_output=True, text=True, encoding="utf-8",
    )
    assert result.returncode == 0, f"Script failed: {result.stderr}"
    return json.loads(result.stdout)


@pytest.fixture
def autopilot_project(tmp_path):
    """Project with 3 sections ready for autopilot build."""
    project = tmp_path / "my-app"
    project.mkdir()
    (project / "agent_docs").mkdir()

    # Run config: pipeline at build step
    run_config = {
        "scope": "full_app",
        "profile": "supabase-nextjs",
        "autonomy": "autonomous",
        "deploy_target": "jelastic-dev",
        "pipeline": ["project", "design", "plan", "build", "test", "changelog", "deploy"],
        "status": "in_progress",
        "current_step": "build",
        "completed_steps": ["project", "design", "plan"],
    }
    (project / "shipwright_run_config.json").write_text(
        json.dumps(run_config, indent=2), encoding="utf-8"
    )

    # Build config: 3 sections, all pending
    build_config = {
        "sections": [
            {"name": "01-models", "status": "pending"},
            {"name": "02-routes", "status": "pending"},
            {"name": "03-ui", "status": "pending"},
        ]
    }
    (project / "shipwright_build_config.json").write_text(
        json.dumps(build_config, indent=2), encoding="utf-8"
    )

    return project


class TestAutopilotFlow:
    """Test the full autopilot build flow using real scripts."""

    def test_initial_progress(self, autopilot_project):
        """get-build-progress shows 3 pending sections."""
        result = run_script_json(ORCHESTRATOR, [
            "get-build-progress",
            "--project-root", str(autopilot_project),
        ])
        assert result["total"] == 3
        assert result["completed"] == 0
        assert result["next_section"] == "01-models"
        assert result["all_done"] is False

    def test_dashboard_initial(self, autopilot_project):
        """Dashboard generates with pending sections."""
        result = run_script_json(DASHBOARD, [
            "--project-root", str(autopilot_project),
            "--session-id", "test-session",
        ])
        assert result["success"] is True

        dashboard = (autopilot_project / "agent_docs" / "build_dashboard.md").read_text(encoding="utf-8")
        assert "0/3" in dashboard
        assert "01-models" in dashboard

    def test_complete_section_1(self, autopilot_project):
        """Complete first section, verify progress updates."""
        # Mark section 1 as complete
        run_script_json(UPDATE_STATE, [
            "--section", "01-models",
            "--status", "complete",
            "--commit", "abc1234",
            "--project-root", str(autopilot_project),
        ])

        # Update dashboard
        run_script_json(DASHBOARD, [
            "--project-root", str(autopilot_project),
            "--section", "01-models",
            "--step", "10",
            "--status", "complete",
            "--session-id", "test-session",
        ])

        # Verify progress
        progress = run_script_json(ORCHESTRATOR, [
            "get-build-progress",
            "--project-root", str(autopilot_project),
        ])
        assert progress["completed"] == 1
        assert progress["next_section"] == "02-routes"

        # Verify dashboard content
        dashboard = (autopilot_project / "agent_docs" / "build_dashboard.md").read_text(encoding="utf-8")
        assert "1/3" in dashboard

    def test_context_pressure_triggers_checkpoint(self, autopilot_project):
        """High tool call count triggers checkpoint recommendation."""
        # Simulate 150 tool calls
        (autopilot_project / ".shipwright_toolcall_count").write_text("150", encoding="utf-8")

        result = run_script_json(PRESSURE, [
            "--counter-file", str(autopilot_project / ".shipwright_toolcall_count"),
            "--threshold", "120",
        ])
        assert result["recommend_checkpoint"] is True
        assert result["tool_calls"] == 150

    def test_no_pressure_below_threshold(self, autopilot_project):
        """Low tool call count does not trigger checkpoint."""
        (autopilot_project / ".shipwright_toolcall_count").write_text("50", encoding="utf-8")

        result = run_script_json(PRESSURE, [
            "--counter-file", str(autopilot_project / ".shipwright_toolcall_count"),
            "--threshold", "120",
        ])
        assert result["recommend_checkpoint"] is False

    def test_full_autopilot_lifecycle(self, autopilot_project):
        """Simulate completing all 3 sections sequentially."""
        sections = ["01-models", "02-routes", "03-ui"]
        commits = ["abc1234", "def5678", "ghi9012"]

        for section, commit in zip(sections, commits):
            # Mark in_progress
            run_script_json(UPDATE_STATE, [
                "--section", section,
                "--status", "in_progress",
                "--project-root", str(autopilot_project),
            ])

            # Dashboard update: in_progress
            run_script_json(DASHBOARD, [
                "--project-root", str(autopilot_project),
                "--section", section,
                "--step", "4",
                "--detail", "Implementing",
                "--session-id", "test-session",
            ])

            # Mark complete
            run_script_json(UPDATE_STATE, [
                "--section", section,
                "--status", "complete",
                "--commit", commit,
                "--project-root", str(autopilot_project),
            ])

            # Dashboard update: complete
            run_script_json(DASHBOARD, [
                "--project-root", str(autopilot_project),
                "--section", section,
                "--step", "10",
                "--status", "complete",
                "--session-id", "test-session",
            ])

        # Final state
        progress = run_script_json(ORCHESTRATOR, [
            "get-build-progress",
            "--project-root", str(autopilot_project),
        ])
        assert progress["all_done"] is True
        assert progress["completed"] == 3
        assert progress["next_section"] is None

        # Final dashboard
        dashboard = (autopilot_project / "agent_docs" / "build_dashboard.md").read_text(encoding="utf-8")
        assert "3/3" in dashboard
        assert "/shipwright-test" in dashboard

    def test_resume_after_checkpoint(self, autopilot_project):
        """Simulate checkpoint mid-build, then resume."""
        # Complete section 1
        run_script_json(UPDATE_STATE, [
            "--section", "01-models",
            "--status", "complete",
            "--commit", "abc1234",
            "--project-root", str(autopilot_project),
        ])

        # Section 2 was in_progress when session ended
        run_script_json(UPDATE_STATE, [
            "--section", "02-routes",
            "--status", "in_progress",
            "--project-root", str(autopilot_project),
        ])

        # Dashboard shows paused
        run_script_json(DASHBOARD, [
            "--project-root", str(autopilot_project),
            "--status", "paused",
            "--session-id", "test-session",
        ])

        dashboard = (autopilot_project / "agent_docs" / "build_dashboard.md").read_text(encoding="utf-8")
        assert "Resume Info" in dashboard
        assert "/shipwright-run" in dashboard

        # New session: get-build-progress should show resume point
        progress = run_script_json(ORCHESTRATOR, [
            "get-build-progress",
            "--project-root", str(autopilot_project),
        ])
        assert progress["completed"] == 1
        assert progress["in_progress"] == 1
        assert progress["next_section"] == "02-routes"  # in_progress takes priority
