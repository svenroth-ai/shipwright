"""Tests for shared/scripts/tools/finalize_iterate.py."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest


@pytest.fixture()
def project(tmp_path):
    """Create a minimal project layout."""
    (tmp_path / "shipwright_run_config.json").write_text(
        json.dumps({"status": "complete", "iterate_history": []}),
        encoding="utf-8",
    )
    (tmp_path / "agent_docs").mkdir()
    (tmp_path / "compliance").mkdir()
    (tmp_path / "shipwright_events.jsonl").write_text("", encoding="utf-8")
    return tmp_path


def test_run_writes_dashboard(project, monkeypatch):
    monkeypatch.chdir(project)
    monkeypatch.delenv("SHIPWRIGHT_SESSION_ID", raising=False)

    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    from tools.finalize_iterate import run

    result = run(project, run_id="test-001")
    assert result["steps"]["dashboard"].get("written")
    assert (project / "agent_docs" / "build_dashboard.md").exists()


def test_run_writes_handoff(project, monkeypatch):
    monkeypatch.chdir(project)
    monkeypatch.delenv("SHIPWRIGHT_SESSION_ID", raising=False)

    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    from tools.finalize_iterate import run

    result = run(project, run_id="test-002")
    assert result["steps"]["handoff"].get("written")
    handoff = project / "agent_docs" / "session_handoff.md"
    assert handoff.exists()
    content = handoff.read_text(encoding="utf-8")
    assert "test-002" in content


def test_run_skips_event_without_commit(project, monkeypatch):
    monkeypatch.chdir(project)

    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    from tools.finalize_iterate import run

    result = run(project, run_id="test-003")
    assert result["steps"]["event"]["skipped"] is True


def test_run_records_event_with_commit(project, monkeypatch):
    monkeypatch.chdir(project)
    monkeypatch.delenv("SHIPWRIGHT_SESSION_ID", raising=False)

    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    from tools.finalize_iterate import run

    result = run(project, run_id="test-004", commit="abc123")
    event_step = result["steps"]["event"]
    assert event_step.get("id") is not None

    events_content = (project / "shipwright_events.jsonl").read_text(encoding="utf-8")
    assert "abc123" in events_content


def test_run_is_idempotent(project, monkeypatch):
    monkeypatch.chdir(project)
    monkeypatch.delenv("SHIPWRIGHT_SESSION_ID", raising=False)

    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    from tools.finalize_iterate import run

    result1 = run(project, run_id="test-005")
    dashboard1 = (project / "agent_docs" / "build_dashboard.md").read_text(encoding="utf-8")

    result2 = run(project, run_id="test-005")
    dashboard2 = (project / "agent_docs" / "build_dashboard.md").read_text(encoding="utf-8")

    assert dashboard1 == dashboard2
    assert result1["steps"]["dashboard"].get("written")
    assert result2["steps"]["dashboard"].get("written")


def test_run_graceful_without_compliance_dir(tmp_path, monkeypatch):
    """No compliance/ dir should not crash."""
    (tmp_path / "shipwright_run_config.json").write_text("{}", encoding="utf-8")
    (tmp_path / "agent_docs").mkdir()
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SHIPWRIGHT_SESSION_ID", raising=False)

    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    from tools.finalize_iterate import run

    result = run(tmp_path, run_id="test-006")
    assert "steps" in result
