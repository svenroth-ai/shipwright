"""Tests for shared/scripts/tools/finalize_iterate.py."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

# C3 (iterate-2026-06-05-fr-linkage-lifecycle): finalize now enforces the
# FR-gate, so every run() that expects a written event must supply a valid
# classification — exactly as a real F5b call does. These tests exercise
# dashboard / handoff / idempotency / attach behaviour, not FR linkage, so the
# minimal tooling classification keeps them focused while satisfying the gate.
_VALID_EXTRAS = {
    "change_type": "tooling",
    "none_reason": "finalize unit test classification",
}


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

    result = run(project, run_id="test-001", event_extras=_VALID_EXTRAS)
    assert result["steps"]["dashboard"].get("written")
    assert (project / ".shipwright" / "agent_docs" / "build_dashboard.md").exists()


def test_run_writes_handoff(project, monkeypatch):
    monkeypatch.chdir(project)
    monkeypatch.delenv("SHIPWRIGHT_SESSION_ID", raising=False)

    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    from tools.finalize_iterate import run

    result = run(project, run_id="test-002", event_extras=_VALID_EXTRAS)
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

    result = run(project, run_id="test-003", event_extras=_VALID_EXTRAS)
    assert result["steps"]["event"].get("id") is not None
    assert "skipped" not in result["steps"]["event"]


def test_run_records_event_with_commit(project, monkeypatch):
    monkeypatch.chdir(project)
    monkeypatch.delenv("SHIPWRIGHT_SESSION_ID", raising=False)

    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    from tools.finalize_iterate import run

    result = run(project, run_id="test-004", commit="abc123", event_extras=_VALID_EXTRAS)
    event_step = result["steps"]["event"]
    assert event_step.get("id") is not None

    events_content = (project / "shipwright_events.jsonl").read_text(encoding="utf-8")
    assert "abc123" in events_content


def test_run_graceful_without_compliance_dir(tmp_path, monkeypatch):
    """No .shipwright/compliance/ dir should not crash."""
    (tmp_path / "shipwright_run_config.json").write_text("{}", encoding="utf-8")
    (tmp_path / ".shipwright" / "agent_docs").mkdir(parents=True, exist_ok=True)
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SHIPWRIGHT_SESSION_ID", raising=False)

    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    from tools.finalize_iterate import run

    result = run(tmp_path, run_id="test-006", event_extras=_VALID_EXTRAS)
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

    result = run(project, run_id="test-reorder-001", reason="iterate test",
                 event_extras=_VALID_EXTRAS)

    event_step = result["steps"]["event"]
    # Event MUST be recorded even without a known commit SHA.
    assert event_step.get("id") is not None
    assert "skipped" not in event_step

    events = [e for e in _read_events_jsonl(project) if e.get("type") == "work_completed"]
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

    run(project, run_id="test-reorder-002", event_extras=_VALID_EXTRAS)

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

    result = run(project, run_id="test-reorder-003", event_extras=_VALID_EXTRAS)
    event_id = result["steps"]["event"]["id"]

    ok = attach_commit_after_finalize(project, event_id, "deadbeef0001")
    assert ok is True

    events = [e for e in _read_events_jsonl(project) if e.get("type") == "work_completed"]
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
    result = run(project, run_id="test-reorder-004", commit="legacy-sha-abc",
                 event_extras=_VALID_EXTRAS)
    assert result["steps"]["event"].get("id") is not None

    events = [e for e in _read_events_jsonl(project) if e.get("type") == "work_completed"]
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

    [event] = [e for e in _read_events_jsonl(project) if e.get("type") == "work_completed"]
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
        "affected_frs": ["FR-01.01"],  # classification so the FR-gate passes
    }
    run(project, run_id="test-spoof-001", event_extras=extras)

    [event] = [e for e in _read_events_jsonl(project) if e.get("type") == "work_completed"]
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

    result = run(project, run_id="test-cli-attach-001", event_extras=_VALID_EXTRAS)
    event_id = result["steps"]["event"]["id"]

    rc = main([
        "attach-commit",
        "--project-root", str(project),
        "--event-id", event_id,
        "--commit", "abc123sha",
    ])
    assert rc == 0

    [event] = [e for e in _read_events_jsonl(project) if e.get("type") == "work_completed"]
    assert event["commit"] == "abc123sha"


# ---------------------------------------------------------------------------
# C3 (iterate-2026-06-05-fr-linkage-lifecycle): finalize FR-gate parity.
# finalize._record_event now runs record_event._fr_or_change_type_gate_error
# BEFORE append_event — an iterate work_completed event lacking FR linkage AND
# a valid change_type+none_reason is rejected, fail-closed (ADR-059 parity).
# Closes the bypass that let the reopen event evt-83b9b73f land for D5 to catch.
# ---------------------------------------------------------------------------


def _import_finalize():
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    from tools import finalize_iterate as fi
    return fi


def test_finalize_rejects_feature_event_without_fr_linkage(project, monkeypatch):
    """AC-1/AC-2: a feature event with no FR and no change_type+none_reason is
    rejected BEFORE write — finalize raises FinalizeGateError, nothing lands."""
    monkeypatch.chdir(project)
    monkeypatch.delenv("SHIPWRIGHT_SESSION_ID", raising=False)
    fi = _import_finalize()

    extras = {"intent": "feature", "spec_impact": "add",
              "description": "reopen-shaped event with no FR"}
    with pytest.raises(fi.FinalizeGateError) as excinfo:
        fi.run(project, run_id="test-gate-reject-001", event_extras=extras)

    # Actionable: the error names the remediation (FR or change_type path).
    msg = str(excinfo.value).lower()
    assert "affected" in msg or "change_type" in msg or "change-type" in msg

    # Fail-closed: no work_completed event was written (no silent degenerate row).
    events = _read_events_jsonl(project)
    assert [e for e in events if e.get("type") == "work_completed"] == []


def test_finalize_allows_feature_event_with_affected_frs(project, monkeypatch):
    """AC-5: a feature event that links an FR passes the gate and is written."""
    monkeypatch.chdir(project)
    monkeypatch.delenv("SHIPWRIGHT_SESSION_ID", raising=False)
    fi = _import_finalize()

    extras = {"intent": "feature", "spec_impact": "add",
              "affected_frs": ["FR-01.01"], "new_frs": ["FR-01.01"]}
    result = fi.run(project, run_id="test-gate-allow-001", event_extras=extras)
    assert result["steps"]["event"].get("id") is not None

    [event] = [e for e in _read_events_jsonl(project) if e.get("type") == "work_completed"]
    assert event["affected_frs"] == ["FR-01.01"]


def test_finalize_allows_event_with_change_type_pair(project, monkeypatch):
    """AC-5: a no-FR iterate classified via change_type+none_reason passes."""
    monkeypatch.chdir(project)
    monkeypatch.delenv("SHIPWRIGHT_SESSION_ID", raising=False)
    fi = _import_finalize()

    extras = {"intent": "change", "change_type": "tooling",
              "none_reason": "internal tooling — no FR touched"}
    result = fi.run(project, run_id="test-gate-allow-002", event_extras=extras)
    assert result["steps"]["event"].get("id") is not None
    [event] = [e for e in _read_events_jsonl(project) if e.get("type") == "work_completed"]
    assert event["change_type"] == "tooling"


def test_finalize_gate_rejects_malformed_change_type(project, monkeypatch):
    """AC-2 parity: change_type present but unrecognized (e.g. an unfilled F5b
    placeholder) is rejected even alongside FRs — matches the CLI gate's
    defense-in-depth (cleaner data on disk)."""
    monkeypatch.chdir(project)
    monkeypatch.delenv("SHIPWRIGHT_SESSION_ID", raising=False)
    fi = _import_finalize()

    extras = {"intent": "change", "affected_frs": ["FR-01.01"],
              "change_type": "{docs|tooling|compliance|infra}"}  # unfilled placeholder
    with pytest.raises(fi.FinalizeGateError):
        fi.run(project, run_id="test-gate-malformed-001", event_extras=extras)
    assert [e for e in _read_events_jsonl(project)
            if e.get("type") == "work_completed"] == []


def test_finalize_gate_preserves_idempotency_without_regating(project, monkeypatch):
    """The idempotency early-return runs BEFORE the gate: a re-run with the
    same run_id but invalid extras returns the existing event id and never
    re-gates (no spurious rejection on operator / Stop-hook re-run)."""
    monkeypatch.chdir(project)
    monkeypatch.delenv("SHIPWRIGHT_SESSION_ID", raising=False)
    fi = _import_finalize()

    first = fi.run(project, run_id="test-gate-idem-001",
                   event_extras={"intent": "change", "change_type": "tooling",
                                 "none_reason": "first valid call"})
    event_id = first["steps"]["event"]["id"]

    # Second call: same run_id, now with INVALID extras (no FR/change_type).
    # Must NOT raise — the early-return short-circuits before the gate.
    second = fi.run(project, run_id="test-gate-idem-001",
                    event_extras={"intent": "feature"})
    assert second["steps"]["event"]["id"] == event_id
    assert len([e for e in _read_events_jsonl(project)
                if e.get("type") == "work_completed"]) == 1


def test_cli_main_returns_1_on_gate_rejection(project, monkeypatch):
    """AC-2: the CLI surfaces the rejection as exit 1 + a structured error,
    matching record_event.main's fail-closed contract (nothing written)."""
    monkeypatch.chdir(project)
    monkeypatch.delenv("SHIPWRIGHT_SESSION_ID", raising=False)
    fi = _import_finalize()

    rc = fi.main([
        "--project-root", str(project),
        "--run-id", "test-gate-cli-001",
        "--event-extras-json", json.dumps({"intent": "feature", "spec_impact": "add"}),
    ])
    assert rc == 1
    assert [e for e in _read_events_jsonl(project)
            if e.get("type") == "work_completed"] == []


def test_finalize_gate_rejection_aborts_artifact_regen(project, monkeypatch):
    """Fail-closed consequence (Stop-hook safety-net behaviour): a gate
    rejection at Step 1 propagates out of run() BEFORE Steps 2-5, so the
    derived artifacts (dashboard / handoff) are NOT refreshed for the
    unclassified iterate. Pins the documented intentional skip — the
    operator must re-run F5b with classification, which regenerates them."""
    monkeypatch.chdir(project)
    monkeypatch.delenv("SHIPWRIGHT_SESSION_ID", raising=False)
    fi = _import_finalize()

    dashboard = project / ".shipwright" / "agent_docs" / "build_dashboard.md"
    handoff = project / ".shipwright" / "agent_docs" / "session_handoff.md"
    assert not dashboard.exists()  # fixture starts clean

    with pytest.raises(fi.FinalizeGateError):
        fi.run(project, run_id="test-gate-abort-001",
               event_extras={"intent": "feature"})  # no FR / change_type

    # Steps 2-5 never ran: no dashboard, no handoff, no event.
    assert not dashboard.exists()
    assert not handoff.exists()
    assert [e for e in _read_events_jsonl(project)
            if e.get("type") == "work_completed"] == []
