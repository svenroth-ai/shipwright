"""Tests for session handoff generation."""

import json

from tools.generate_session_handoff import generate_handoff


def test_generate_handoff_empty_project(tmp_project):
    content = generate_handoff(tmp_project, session_id="test-123", reason="test")
    assert "# Session Handoff" in content
    assert "test-123" in content
    assert "not_started" in content
    assert "test" in content


def test_generate_handoff_with_configs(project_with_configs):
    content = generate_handoff(project_with_configs, session_id="sess-456")
    assert "sess-456" in content
    assert "build" in content
    assert "shipwright_run_config.json" in content
    assert "exists" in content


def test_generate_handoff_includes_all_required_fields(tmp_project):
    content = generate_handoff(tmp_project)
    # Required fields from template
    assert "Session ID" in content
    assert "Timestamp" in content
    assert "Reason" in content
    assert "Phase" in content
    assert "Config Files to Read" in content


def test_generate_handoff_renders_last_iterate_when_history_present(tmp_project):
    """Iterate 11.3 — run_config.iterate_history[-1] becomes a 'Last Iterate'
    section so the handoff reflects iterate state instead of stale build state."""
    run_cfg = {
        "status": "complete",
        "iterate_history": [
            {
                "run_id": "iterate-2026-04-13-foo",
                "date": "2026-04-13",
                "type": "feature",
                "complexity": "small",
                "branch": "iterate/foo",
                "tests_passed": True,
            },
            {
                "run_id": "iterate-2026-04-14-bar",
                "date": "2026-04-14",
                "type": "bug",
                "complexity": "medium",
                "branch": "iterate/bar",
                "adr_id": "ADR-019",
                "description": "fix inbox filter",
                "tests_passed": True,
            },
        ],
    }
    (tmp_project / "shipwright_run_config.json").write_text(
        json.dumps(run_cfg), encoding="utf-8"
    )

    content = generate_handoff(tmp_project, reason="iterate completion: iterate-2026-04-14-bar")
    assert "## Last Iterate" in content
    # The last entry wins, not the first
    assert "iterate-2026-04-14-bar" in content
    assert "iterate-2026-04-13-foo" not in content
    assert "ADR-019" in content
    assert "fix inbox filter" in content
    assert "iterate/bar" in content
    # Reason passes through
    assert "iterate completion: iterate-2026-04-14-bar" in content
    # Legacy build state block is still present (renamed from Current State)
    assert "## Legacy build state" in content


def test_generate_handoff_omits_last_iterate_when_no_history(tmp_project):
    """Without iterate_history, no 'Last Iterate' section is rendered."""
    content = generate_handoff(tmp_project)
    assert "## Last Iterate" not in content
    # Legacy block always rendered
    assert "## Legacy build state" in content


def test_generate_handoff_with_decision_log(project_with_configs):
    # Create a decision log
    log_path = project_with_configs / "agent_docs" / "decision_log.md"
    log_path.write_text(
        "# Decision Log\n\n## ADR-001 | 2026-03-20 | Auth | Commit abc\n\n### Decision\nUse JWT\n",
        encoding="utf-8",
    )

    content = generate_handoff(project_with_configs)
    assert "Recent Decisions" in content
    assert "ADR-001" in content
