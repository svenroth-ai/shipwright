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


def test_canon_frontmatter_prepended_at_top(tmp_project):
    """Iterate 12.1: when canon_frontmatter dict is passed, the handoff
    starts with a YAML block that stop-hook's parser can recognise."""
    fm = {
        "run_id": "project-20260414-alpha",
        "phase": "project",
        "reason": "project scaffolding complete",
        "timestamp": "2026-04-14T10:00:00Z",
    }
    content = generate_handoff(tmp_project, session_id="s1", canon_frontmatter=fm)
    assert content.startswith("---\ncanon_generated: true\n")
    assert 'run_id: "project-20260414-alpha"' in content
    assert 'phase: "project"' in content
    # Legacy body still follows the frontmatter
    assert "# Session Handoff" in content


def test_canon_frontmatter_omitted_by_default(tmp_project):
    """Without the kwarg, the handoff body is unchanged (backwards compat)."""
    content = generate_handoff(tmp_project, session_id="s1")
    assert not content.startswith("---\n")
    assert content.lstrip().startswith("# Session Handoff")


def test_cli_canon_marker_requires_run_id_env(tmp_project, monkeypatch, capsys):
    """Iterate 12.1 safe-degrade: --canon-marker without SHIPWRIGHT_RUN_ID
    drops the marker and emits a stderr warning; handoff is still written."""
    import sys as _sys
    from unittest.mock import patch

    monkeypatch.delenv("SHIPWRIGHT_RUN_ID", raising=False)

    argv = [
        "generate_session_handoff.py",
        "--project-root", str(tmp_project),
        "--canon-marker",
        "--phase", "project",
        "--reason", "test",
    ]
    with patch.object(_sys, "argv", argv):
        from tools.generate_session_handoff import main as handoff_main
        handoff_main()

    captured = capsys.readouterr()
    assert "SHIPWRIGHT_RUN_ID is unset" in captured.err
    handoff = tmp_project / "agent_docs" / "session_handoff.md"
    assert handoff.exists()
    # Safe-degrade: NO frontmatter written
    assert not handoff.read_text(encoding="utf-8").startswith("---\n")


def test_cli_canon_marker_writes_frontmatter_when_run_id_set(tmp_project, monkeypatch):
    """With SHIPWRIGHT_RUN_ID set, the CLI writes the canon frontmatter."""
    import sys as _sys
    from unittest.mock import patch

    monkeypatch.setenv("SHIPWRIGHT_RUN_ID", "project-20260414-test")

    argv = [
        "generate_session_handoff.py",
        "--project-root", str(tmp_project),
        "--canon-marker",
        "--phase", "project",
        "--reason", "project scaffolding complete",
    ]
    with patch.object(_sys, "argv", argv):
        from tools.generate_session_handoff import main as handoff_main
        handoff_main()

    content = (tmp_project / "agent_docs" / "session_handoff.md").read_text(encoding="utf-8")
    assert content.startswith("---\n")
    assert 'run_id: "project-20260414-test"' in content
    assert 'phase: "project"' in content


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
