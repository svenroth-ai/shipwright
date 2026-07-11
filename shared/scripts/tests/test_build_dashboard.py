"""Tests for update_build_dashboard.py."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.update_build_dashboard import generate_dashboard, format_status, STEP_LABELS


@pytest.fixture
def tmp_project(tmp_path):
    (tmp_path / ".shipwright" / "agent_docs").mkdir(parents=True, exist_ok=True)
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
        "pipeline": ["project", "design", "plan", "build", "test", "changelog", "deploy"],
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

    def test_pipeline_multi_split_shows_latest_end_ts(self, tmp_project):
        """A multi-split phase records one phase_completed per split; the Pipeline
        'Completed' column must show the LATEST split's date (the phase's true
        end), not the first (iterate-2026-07-11-phase-completed-per-split)."""
        _write_events(tmp_project, [
            {"v": 1, "type": "phase_completed", "phase": "build",
             "splitId": "01-foundation", "ts": "2026-04-01T09:00:00Z"},
            {"v": 1, "type": "phase_completed", "phase": "build",
             "splitId": "03-api", "ts": "2026-04-03T18:00:00Z"},
            {"v": 1, "type": "phase_completed", "phase": "build",
             "splitId": "02-ui", "ts": "2026-04-02T12:00:00Z"},
        ])
        content = generate_dashboard(tmp_project, session_id="test")
        assert "| build | complete | 2026-04-03 |" in content
        assert "2026-04-01" not in content  # not the first split's ts


class TestMultiSplit:
    def test_dashboard_multi_split_pipeline_shows_total(self, tmp_project):
        """Pipeline row shows total progress across all splits."""
        run_config = {
            "pipeline": ["project", "plan", "build", "test"],
            "completed_steps": ["project", "plan"],
            "current_step": "build",
        }
        build_config = {
            "current_split": "02-dashboard",
            "completed_splits": ["01-auth"],
            "split_01_sections": [
                {"name": "01-login", "status": "complete", "commit": "aaa"},
                {"name": "02-rbac", "status": "complete", "commit": "bbb"},
            ],
            "sections": [
                {"name": "01-widgets", "status": "complete", "commit": "ccc"},
                {"name": "02-charts", "status": "pending"},
            ],
        }
        project_config = {
            "splits": [
                {"name": "01-auth", "status": "complete"},
                {"name": "02-dashboard", "status": "in_progress"},
            ],
        }
        (tmp_project / "shipwright_run_config.json").write_text(
            json.dumps(run_config), encoding="utf-8"
        )
        (tmp_project / "shipwright_build_config.json").write_text(
            json.dumps(build_config), encoding="utf-8"
        )
        (tmp_project / "shipwright_project_config.json").write_text(
            json.dumps(project_config), encoding="utf-8"
        )
        content = generate_dashboard(tmp_project, session_id="test")
        assert "3/4 sections" in content  # total across all splits
        assert "02-dashboard" in content  # split label shown
        assert "01-login" not in content  # archived sections NOT in table

    def test_dashboard_split_complete_not_build_complete(self, tmp_project):
        """Split done but more splits remain — shows 'Split complete'."""
        build_config = {
            "current_split": "01-auth",
            "completed_splits": [],
            "sections": [
                {"name": "01-login", "status": "complete", "commit": "aaa"},
            ],
        }
        project_config = {
            "splits": [
                {"name": "01-auth", "status": "complete"},
                {"name": "02-dashboard", "status": "pending"},
            ],
        }
        (tmp_project / "shipwright_build_config.json").write_text(
            json.dumps(build_config), encoding="utf-8"
        )
        (tmp_project / "shipwright_project_config.json").write_text(
            json.dumps(project_config), encoding="utf-8"
        )
        content = generate_dashboard(tmp_project, session_id="test")
        assert "Split 01-auth complete" in content
        assert "/shipwright-run" in content
        assert "/shipwright-test" not in content

    def test_dashboard_all_splits_done(self, tmp_project):
        """All splits complete — shows 'Ready for /shipwright-test'."""
        build_config = {
            "current_split": "01-auth",
            "completed_splits": [],
            "sections": [
                {"name": "01-login", "status": "complete", "commit": "aaa"},
            ],
        }
        project_config = {
            "splits": [{"name": "01-auth", "status": "complete"}],
        }
        (tmp_project / "shipwright_build_config.json").write_text(
            json.dumps(build_config), encoding="utf-8"
        )
        (tmp_project / "shipwright_project_config.json").write_text(
            json.dumps(project_config), encoding="utf-8"
        )
        content = generate_dashboard(tmp_project, session_id="test")
        assert "/shipwright-test" in content


def _write_events(project_root: Path, events: list[dict]):
    """Helper to write events to shipwright_events.jsonl."""
    lines = [json.dumps(e) for e in events]
    (project_root / "shipwright_events.jsonl").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )


class TestEventTestStatus:
    def test_status_from_test_run_event(self, tmp_project):
        """test_run events render layered test status."""
        _write_events(tmp_project, [
            {"v": 1, "type": "test_run", "ts": "2026-04-02T10:00:00Z",
             "trigger": "pipeline", "layers": {
                 "unit": {"passed": 715, "total": 715},
                 "e2e": {"passed": 0, "total": 0},
                 "smoke": {"status": "pass"},
             }},
        ])
        content = generate_dashboard(tmp_project, session_id="test")
        assert "## Test Status" in content
        assert "Unit: 715/715" in content
        assert "(iterate)" not in content

    def test_status_from_iterate_with_results_json(self, tmp_project):
        """Iterate events use shipwright_test_results.json for layered data."""
        _write_events(tmp_project, [
            {"v": 1, "type": "test_run", "ts": "2026-04-02T10:00:00Z",
             "trigger": "pipeline", "layers": {
                 "unit": {"passed": 715, "total": 715},
             }},
            {"v": 1, "type": "work_completed", "source": "iterate",
             "ts": "2026-04-06T10:00:00Z", "intent": "feature",
             "description": "Add search", "tests": {"passed": 830, "total": 831}},
        ])
        (tmp_project / "shipwright_test_results.json").write_text(json.dumps({
            "iterate_latest": {
                "date": "2026-04-06",
                "unit": {"passed": 830, "total": 831, "status": "failed"},
                "e2e": {"passed": 0, "total": 0, "status": "not_run"},
                "smoke": {"status": "pass"},
            }
        }), encoding="utf-8")
        content = generate_dashboard(tmp_project, session_id="test")
        assert "## Test Status" in content
        assert "Unit: 830/831" in content
        assert "(iterate)" in content
        assert "2026-04-06" in content

    def test_status_from_iterate_flat_fallback(self, tmp_project):
        """When no results JSON, iterate events show flat passed/total."""
        _write_events(tmp_project, [
            {"v": 1, "type": "work_completed", "source": "iterate",
             "ts": "2026-04-06T10:00:00Z", "intent": "feature",
             "description": "Add search",
             "tests": {"passed": 830, "total": 831, "e2e_run": True}},
        ])
        content = generate_dashboard(tmp_project, session_id="test")
        assert "## Test Status" in content
        assert "Tests: 830/831" in content
        assert "(incl. E2E)" in content
        assert "(iterate)" in content

    def test_status_prefers_newer_iterate(self, tmp_project):
        """When iterate event is newer than test_run, iterate data is used."""
        _write_events(tmp_project, [
            {"v": 1, "type": "test_run", "ts": "2026-04-02T10:00:00Z",
             "trigger": "pipeline", "layers": {
                 "unit": {"passed": 715, "total": 715},
             }},
            {"v": 1, "type": "work_completed", "source": "iterate",
             "ts": "2026-04-06T10:00:00Z", "intent": "change",
             "description": "Fix bug",
             "tests": {"passed": 830, "total": 831}},
        ])
        content = generate_dashboard(tmp_project, session_id="test")
        assert "(iterate)" in content
        assert "830/831" in content

    def test_status_prefers_newer_test_run(self, tmp_project):
        """When test_run is newer than iterate event, test_run data is used."""
        _write_events(tmp_project, [
            {"v": 1, "type": "work_completed", "source": "iterate",
             "ts": "2026-04-01T10:00:00Z", "intent": "change",
             "description": "Fix bug",
             "tests": {"passed": 830, "total": 831}},
            {"v": 1, "type": "test_run", "ts": "2026-04-06T10:00:00Z",
             "trigger": "pipeline", "layers": {
                 "unit": {"passed": 831, "total": 831},
             }},
        ])
        content = generate_dashboard(tmp_project, session_id="test")
        assert "(iterate)" not in content
        assert "Unit: 831/831" in content

    def test_no_test_status_without_data(self, tmp_project):
        """No Test Status section if no test_run or iterate events."""
        _write_events(tmp_project, [
            {"v": 1, "type": "phase_completed", "ts": "2026-04-01T10:00:00Z",
             "phase": "project"},
        ])
        content = generate_dashboard(tmp_project, session_id="test")
        assert "## Test Status" not in content


class TestStepLabels:
    def test_all_steps_have_labels(self):
        for i in range(1, 13):
            assert i in STEP_LABELS


class TestRunIdEmbed:
    """F5b renders the iterate run_id into the dashboard header so the
    finalization verifier (check_build_dashboard_has_run_id) passes
    deterministically — the F6 commit SHA cannot be in an F5b dashboard
    (F5b precedes the F6 commit and the F7 event)."""

    def test_run_id_embedded_in_header_when_provided(self, tmp_project):
        content = generate_dashboard(
            tmp_project, phase="iterate", session_id="s",
            run_id="iterate-20260516-foo",
        )
        assert "| Run: iterate-20260516-foo" in content

    def test_no_run_id_line_when_absent(self, tmp_project):
        """Stop hook / non-iterate phases pass no run_id — header unchanged."""
        content = generate_dashboard(tmp_project, session_id="s")
        assert "| Run:" not in content

    def test_run_id_embedded_in_event_based_dashboard(self, tmp_project):
        """The event-sourced dashboard path also embeds the run_id."""
        (tmp_project / "shipwright_events.jsonl").write_text(
            json.dumps({"v": 1, "id": "evt-x", "ts": "2026-05-16T00:00:00Z",
                        "type": "work_completed", "source": "iterate",
                        "commit": "abc1234", "intent": "bug",
                        "description": "x"}) + "\n",
            encoding="utf-8",
        )
        content = generate_dashboard(
            tmp_project, phase="iterate", session_id="s",
            run_id="iterate-20260516-bar",
        )
        assert "| Run: iterate-20260516-bar" in content
        assert "Recent Changes" in content  # confirms the event path was taken


class TestRecentChangesTypeColumn:
    """The Recent Changes Type column must render a clean token, never a
    free-text description leaked into the event ``intent`` field."""

    def test_freetext_intent_collapses_to_change(self, tmp_project):
        (tmp_project / "shipwright_events.jsonl").write_text(
            json.dumps({"v": 1, "id": "evt-x", "ts": "2026-05-20T00:00:00Z",
                        "type": "work_completed", "source": "iterate",
                        "commit": "abc1234",
                        "intent": "Clear 5 compliance triage bloat items (G2 stoplist)",
                        "description": "Some change",
                        "change_type": "compliance"}) + "\n",
            encoding="utf-8",
        )
        content = generate_dashboard(tmp_project, phase="iterate", session_id="s")
        recent_block = content.split("## Recent Changes")[1].split("## ")[0]
        assert "| change | Some change |" in recent_block
        assert "Clear 5 compliance triage bloat" not in recent_block

    def test_alias_intent_normalized(self, tmp_project):
        (tmp_project / "shipwright_events.jsonl").write_text(
            json.dumps({"v": 1, "id": "evt-y", "ts": "2026-05-20T00:00:00Z",
                        "type": "work_completed", "source": "iterate",
                        "commit": "def5678", "intent": "fix",
                        "description": "Some fix"}) + "\n",
            encoding="utf-8",
        )
        content = generate_dashboard(tmp_project, phase="iterate", session_id="s")
        recent_block = content.split("## Recent Changes")[1].split("## ")[0]
        assert "| bug | Some fix |" in recent_block


class TestFrColumnFallback:
    """The FRs column prefers affected_frs; if absent, it falls back to the
    change_type tag (docs/tooling/compliance/infra) so non-FR iterates show
    their classification instead of an empty cell. See Iterate C.1."""

    def test_affected_frs_takes_precedence(self, tmp_project):
        (tmp_project / "shipwright_events.jsonl").write_text(
            json.dumps({"v": 1, "id": "evt-a", "ts": "2026-05-20T00:00:00Z",
                        "type": "work_completed", "source": "iterate",
                        "commit": "abc1234", "intent": "feature",
                        "description": "x",
                        "affected_frs": ["FR-01.07"],
                        "change_type": "tooling"}) + "\n",
            encoding="utf-8",
        )
        content = generate_dashboard(tmp_project, phase="iterate", session_id="s")
        # FR wins; tooling tag must NOT appear in the recent-changes row.
        recent_block = content.split("## Recent Changes")[1].split("##")[0]
        assert "FR-01.07" in recent_block
        assert "| tooling |" not in recent_block

    def test_change_type_used_when_no_frs(self, tmp_project):
        (tmp_project / "shipwright_events.jsonl").write_text(
            json.dumps({"v": 1, "id": "evt-b", "ts": "2026-05-20T00:00:00Z",
                        "type": "work_completed", "source": "iterate",
                        "commit": "def4567", "intent": "bug",
                        "description": "y",
                        "change_type": "tooling"}) + "\n",
            encoding="utf-8",
        )
        content = generate_dashboard(tmp_project, phase="iterate", session_id="s")
        recent_block = content.split("## Recent Changes")[1].split("##")[0]
        assert "| tooling |" in recent_block

    def test_empty_when_neither_set(self, tmp_project):
        (tmp_project / "shipwright_events.jsonl").write_text(
            json.dumps({"v": 1, "id": "evt-c", "ts": "2026-05-20T00:00:00Z",
                        "type": "work_completed", "source": "iterate",
                        "commit": "ghi7890", "intent": "change",
                        "description": "z"}) + "\n",
            encoding="utf-8",
        )
        content = generate_dashboard(tmp_project, phase="iterate", session_id="s")
        recent_block = content.split("## Recent Changes")[1].split("##")[0]
        # Row exists but FR cell is empty (whitespace between two pipes).
        assert "| ghi7890 |  |" in recent_block
