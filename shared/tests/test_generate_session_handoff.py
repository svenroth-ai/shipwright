"""Tests for session handoff generation."""

import json
from datetime import datetime, timedelta, timezone

from tools.generate_session_handoff import (
    _current_iterate_progress,
    generate_handoff,
)


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


# ---------------------------------------------------------------------------
# Iterate 14.15 — Resume safeguard: `_current_iterate_progress` must surface
# enough evidence for B1 Resume to decide whether External Review is pending.
# ---------------------------------------------------------------------------


def _write_iterate_spec(
    project_root, *, run_id: str, complexity: str, branch_tail: str
) -> None:
    """Create a minimal iterate spec file matching a branch tail."""
    iterate_dir = project_root / "planning" / "iterate"
    iterate_dir.mkdir(parents=True, exist_ok=True)
    spec = iterate_dir / f"2026-04-17-{branch_tail}.md"
    spec.write_text(
        "\n".join([
            f"# Iterate Spec: {branch_tail}",
            "",
            f"- **Run ID:** {run_id}",
            "- **Type:** feature",
            f"- **Complexity:** {complexity}",
            "- **Status:** draft",
        ]),
        encoding="utf-8",
    )


def test_current_iterate_progress_off_branch_returns_empty(tmp_project):
    """Non-iterate branches produce no section — avoids polluting the handoff
    during normal pipeline work."""
    assert _current_iterate_progress(tmp_project, {"branch": "main"}) == []
    assert _current_iterate_progress(tmp_project, {"branch": ""}) == []


def test_current_iterate_progress_flags_missing_review_on_medium(tmp_project):
    """Medium+ iterate with no external review marker must be flagged so B1
    Resume runs Step 4 before dispatching to the Remaining phase."""
    _write_iterate_spec(
        tmp_project,
        run_id="iterate-2026-04-17-foo",
        complexity="medium",
        branch_tail="foo",
    )
    git_info = {"branch": "iterate/foo", "uncommitted_changes": ""}

    lines = _current_iterate_progress(tmp_project, git_info)
    text = "\n".join(lines)

    assert "## Current Iterate Progress" in text
    assert "iterate/foo" in text
    assert "iterate-2026-04-17-foo" in text
    assert "Complexity" in text and "medium" in text
    assert "External Review Marker" in text and "missing" in text
    assert "Mandatory replay on Resume" in text
    assert "External LLM Review" in text


def test_current_iterate_progress_fresh_marker_clears_replay(tmp_project):
    """A run-scoped marker file proves Step 4 ran — no replay needed."""
    _write_iterate_spec(
        tmp_project,
        run_id="iterate-2026-04-17-bar",
        complexity="medium",
        branch_tail="bar",
    )
    marker = tmp_project / "planning" / "iterate" / "iterate-2026-04-17-bar-external-review.json"
    marker.write_text(
        json.dumps({
            "status": "completed",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "provider": "openrouter",
            "findings_count": 2,
        }),
        encoding="utf-8",
    )

    lines = _current_iterate_progress(tmp_project, {"branch": "iterate/bar"})
    text = "\n".join(lines)

    assert "External Review Marker" in text and "completed" in text
    assert "Mandatory replay on Resume" not in text


def test_current_iterate_progress_stale_shared_marker_is_replay_trigger(tmp_project):
    """A shared `external_review_state.json` predating the current spec means
    the marker is for a prior run — must still trigger replay."""
    _write_iterate_spec(
        tmp_project,
        run_id="iterate-2026-04-17-baz",
        complexity="medium",
        branch_tail="baz",
    )
    marker = tmp_project / "planning" / "iterate" / "external_review_state.json"
    # Marker written 2 days before the spec file was created
    stale_ts = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    marker.write_text(
        json.dumps({
            "status": "completed",
            "timestamp": stale_ts,
            "provider": "openrouter",
        }),
        encoding="utf-8",
    )
    # Force the marker's filesystem mtime older than the spec
    import os
    spec_path = tmp_project / "planning" / "iterate" / "2026-04-17-baz.md"
    now = datetime.now(timezone.utc).timestamp()
    os.utime(marker, (now - 2 * 86400, now - 2 * 86400))
    os.utime(spec_path, (now, now))

    lines = _current_iterate_progress(tmp_project, {"branch": "iterate/baz"})
    text = "\n".join(lines)

    assert "stale" in text
    assert "Mandatory replay on Resume" in text


def test_current_iterate_progress_trivial_skips_review_replay(tmp_project):
    """Trivial/small iterates never require external review — replay should
    not flag it even without a marker."""
    _write_iterate_spec(
        tmp_project,
        run_id="iterate-2026-04-17-qux",
        complexity="small",
        branch_tail="qux",
    )

    lines = _current_iterate_progress(tmp_project, {"branch": "iterate/qux"})
    text = "\n".join(lines)

    assert "External Review Marker" in text and "missing" in text
    # Small complexity: no replay section should be rendered for review
    assert "External LLM Review" not in text
