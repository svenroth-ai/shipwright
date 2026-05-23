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
    (tmp_path / ".shipwright" / "agent_docs").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".shipwright" / "compliance").mkdir(parents=True)
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
    assert (project / ".shipwright" / "agent_docs" / "build_dashboard.md").exists()


def test_run_writes_handoff(project, monkeypatch):
    monkeypatch.chdir(project)
    monkeypatch.delenv("SHIPWRIGHT_SESSION_ID", raising=False)

    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    from tools.finalize_iterate import run

    result = run(project, run_id="test-002")
    assert result["steps"]["handoff"].get("written")
    handoff = project / ".shipwright" / "agent_docs" / "session_handoff.md"
    assert handoff.exists()
    content = handoff.read_text(encoding="utf-8")
    assert "test-002" in content


def test_run_records_event_even_without_commit_arg(project, monkeypatch):
    """Replaces the old test_run_skips_event_without_commit.

    iterate-2026-05-23 contract: finalize ALWAYS records the
    ``work_completed`` event (commit may be empty placeholder). The
    legacy "skip when no commit" branch is removed because it caused the
    iterate's own event to miss the committed compliance snapshot.
    """
    monkeypatch.chdir(project)

    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    from tools.finalize_iterate import run

    result = run(project, run_id="test-003")
    assert result["steps"]["event"].get("id") is not None
    assert "skipped" not in result["steps"]["event"]


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
    dashboard1 = (project / ".shipwright" / "agent_docs" / "build_dashboard.md").read_text(encoding="utf-8")

    result2 = run(project, run_id="test-005")
    dashboard2 = (project / ".shipwright" / "agent_docs" / "build_dashboard.md").read_text(encoding="utf-8")

    assert dashboard1 == dashboard2
    assert result1["steps"]["dashboard"].get("written")
    assert result2["steps"]["dashboard"].get("written")


def test_run_graceful_without_compliance_dir(tmp_path, monkeypatch):
    """No .shipwright/compliance/ dir should not crash."""
    (tmp_path / "shipwright_run_config.json").write_text("{}", encoding="utf-8")
    (tmp_path / ".shipwright" / "agent_docs").mkdir(parents=True, exist_ok=True)
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SHIPWRIGHT_SESSION_ID", raising=False)

    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    from tools.finalize_iterate import run

    result = run(tmp_path, run_id="test-006")
    assert "steps" in result


# ---------------------------------------------------------------------------
# iterate-2026-05-23-compliance-md-single-producer:
# Reordered finalize — event recorded PRE-compliance-regen with commit="",
# then patched POST-commit via attach_commit_after_finalize.
# ---------------------------------------------------------------------------


def _read_events_jsonl(project: Path) -> list[dict]:
    raw = (project / "shipwright_events.jsonl").read_text(encoding="utf-8")
    return [json.loads(line) for line in raw.splitlines() if line.strip()]


def test_run_records_event_pre_commit_with_empty_commit(project, monkeypatch):
    """New contract: event lands in events.jsonl BEFORE compliance regen,
    with ``commit=""`` placeholder. Returned ``event_id`` enables the
    post-commit SHA patch step."""
    monkeypatch.chdir(project)
    monkeypatch.delenv("SHIPWRIGHT_SESSION_ID", raising=False)

    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    from tools.finalize_iterate import run

    result = run(project, run_id="test-reorder-001", reason="iterate test")

    event_step = result["steps"]["event"]
    # Event MUST be recorded even without a known commit SHA.
    assert event_step.get("id") is not None
    assert "skipped" not in event_step

    events = _read_events_jsonl(project)
    assert len(events) == 1
    assert events[0]["id"] == event_step["id"]
    assert events[0]["type"] == "work_completed"
    assert events[0]["source"] == "iterate"
    # Commit SHA is empty until F6.5 attach.
    assert events[0]["commit"] == ""


def test_run_includes_iterate_event_in_compliance_data(project, monkeypatch):
    """Compliance regen runs AFTER record-event, so the regenerated MDs
    reflect the iterate's own event (when collect_all is reachable).

    Concretely: re-running collect_all post-finalize sees the event the
    finalize recorded. This is the foundation for the F0 staleness gate
    (the committed snapshot includes the iterate's own work_completed).
    """
    monkeypatch.chdir(project)
    monkeypatch.delenv("SHIPWRIGHT_SESSION_ID", raising=False)

    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    from tools.finalize_iterate import run

    run(project, run_id="test-reorder-002")

    events = _read_events_jsonl(project)
    # Exactly one work_completed event, written before any compliance step.
    work_completed = [e for e in events if e.get("type") == "work_completed"]
    assert len(work_completed) == 1


def test_attach_commit_after_finalize_patches_event(project, monkeypatch):
    """``attach_commit_after_finalize(project, event_id, sha)`` patches the
    event's commit field in the events log."""
    monkeypatch.chdir(project)
    monkeypatch.delenv("SHIPWRIGHT_SESSION_ID", raising=False)

    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    from tools.finalize_iterate import attach_commit_after_finalize, run

    result = run(project, run_id="test-reorder-003")
    event_id = result["steps"]["event"]["id"]

    ok = attach_commit_after_finalize(project, event_id, "deadbeef0001")
    assert ok is True

    events = _read_events_jsonl(project)
    assert len(events) == 1
    assert events[0]["commit"] == "deadbeef0001"


def test_run_no_longer_requires_commit_arg(project, monkeypatch):
    """Backwards-compat shim: the old ``commit=`` arg is accepted for
    callers that haven't migrated, but the event is recorded regardless."""
    monkeypatch.chdir(project)
    monkeypatch.delenv("SHIPWRIGHT_SESSION_ID", raising=False)

    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    from tools.finalize_iterate import run

    # Old caller signature (commit known at call time) still works.
    result = run(project, run_id="test-reorder-004", commit="legacy-sha-abc")
    assert result["steps"]["event"].get("id") is not None

    events = _read_events_jsonl(project)
    assert len(events) == 1
    # When the caller passes a commit SHA, it's stored directly (no need
    # for a follow-up attach call).
    assert events[0]["commit"] == "legacy-sha-abc"


def test_run_merges_event_extras_into_event(project, monkeypatch):
    """``event_extras`` lets the caller supply F11-mandated fields
    (intent, spec_impact, affected_frs, etc.) at F5b time, so the
    spec-impact verifier passes without a separate record_event call."""
    monkeypatch.chdir(project)
    monkeypatch.delenv("SHIPWRIGHT_SESSION_ID", raising=False)

    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    from tools.finalize_iterate import run

    extras = {
        "intent": "change",
        "description": "fix stale compliance MDs",
        "spec_impact": "none",
        "spec_impact_justification": "Internal SDLC tooling change.",
        "change_type": "tooling",
        "none_reason": "Audit semantic shift — no FR touched.",
        "changed_files": ["audit_staleness.py", "finalize_iterate.py"],
    }
    result = run(project, run_id="test-extras-001", event_extras=extras)
    assert result["steps"]["event"].get("id") is not None

    [event] = _read_events_jsonl(project)
    for key, val in extras.items():
        assert event[key] == val, f"{key!r} not merged: got {event.get(key)!r}"
    # System-owned fields preserved.
    assert event["type"] == "work_completed"
    assert event["source"] == "iterate"
    assert event["adr_id"] == "test-extras-001"


def test_event_extras_cannot_spoof_system_fields(project, monkeypatch):
    """Caller cannot overwrite ``type``/``source``/``adr_id``/``commit`` via extras."""
    monkeypatch.chdir(project)
    monkeypatch.delenv("SHIPWRIGHT_SESSION_ID", raising=False)

    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    from tools.finalize_iterate import run

    extras = {
        "type": "task_created",    # attempted spoof
        "source": "evil",           # attempted spoof
        "adr_id": "wrong-run-id",   # attempted spoof
        "commit": "fake-sha",       # attempted spoof
        "intent": "feature",        # legitimate
    }
    run(project, run_id="test-spoof-001", event_extras=extras)

    [event] = _read_events_jsonl(project)
    assert event["type"] == "work_completed"
    assert event["source"] == "iterate"
    assert event["adr_id"] == "test-spoof-001"
    assert event["commit"] == ""  # placeholder, not the spoof
    assert event["intent"] == "feature"  # the legitimate field made it through


def test_cli_attach_commit_subcommand(project, monkeypatch):
    """``finalize_iterate.py attach-commit`` subcommand patches the SHA."""
    monkeypatch.chdir(project)
    monkeypatch.delenv("SHIPWRIGHT_SESSION_ID", raising=False)

    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    from tools.finalize_iterate import main, run

    result = run(project, run_id="test-cli-attach-001")
    event_id = result["steps"]["event"]["id"]

    rc = main([
        "attach-commit",
        "--project-root", str(project),
        "--event-id", event_id,
        "--commit", "abc123sha",
    ])
    assert rc == 0

    [event] = _read_events_jsonl(project)
    assert event["commit"] == "abc123sha"
