"""Tests for session handoff generation."""

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
