"""iterate-2026-08-16-fr-gate-test-evidence: F5b (finalize_iterate.py)
write-path parity for the test-evidence gate.

`_record_event` calls `run_fr_gates`, which now includes
`missing_test_evidence_error` — so a behavior-affecting, FR-declaring event with
no test evidence must be rejected here exactly as it is at the
`record_event.py` CLI (ADR-059 parity). Kept in its own file (not appended to
the baseline-capped `test_finalize_iterate.py`) per the existing convention.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture()
def project(tmp_path):
    (tmp_path / "shipwright_run_config.json").write_text(
        json.dumps({"status": "complete", "iterate_history": []}),
        encoding="utf-8",
    )
    (tmp_path / ".shipwright" / "agent_docs").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".shipwright" / "compliance").mkdir(parents=True)
    (tmp_path / "shipwright_events.jsonl").write_text("", encoding="utf-8")
    return tmp_path


def _read_events_jsonl(project: Path) -> list[dict]:
    raw = (project / "shipwright_events.jsonl").read_text(encoding="utf-8")
    return [json.loads(line) for line in raw.splitlines() if line.strip()]


def test_finalize_rejects_behavior_affecting_frs_without_evidence(project, monkeypatch):
    monkeypatch.chdir(project)
    monkeypatch.delenv("SHIPWRIGHT_SESSION_ID", raising=False)
    from tools import finalize_iterate as fi

    extras = {"intent": "change", "spec_impact": "modify", "affected_frs": ["FR-01.01"]}
    with pytest.raises(fi.FinalizeGateError) as excinfo:
        fi.run(project, run_id="test-evidence-reject-001", event_extras=extras)
    assert "test evidence" in str(excinfo.value).lower()
    assert [e for e in _read_events_jsonl(project) if e.get("type") == "work_completed"] == []


def test_finalize_allows_no_tests_reason(project, monkeypatch):
    monkeypatch.chdir(project)
    monkeypatch.delenv("SHIPWRIGHT_SESSION_ID", raising=False)
    from tools import finalize_iterate as fi

    extras = {
        "intent": "change", "spec_impact": "modify", "affected_frs": ["FR-01.01"],
        "no_tests_reason": "no test-results ledger in this fixture",
    }
    result = fi.run(project, run_id="test-evidence-allow-001", event_extras=extras)
    assert result["steps"]["event"].get("id") is not None
    [event] = [e for e in _read_events_jsonl(project) if e.get("type") == "work_completed"]
    assert event["no_tests_reason"] == "no test-results ledger in this fixture"


def test_finalize_allows_explicit_tests_block(project, monkeypatch):
    """A caller-supplied `tests` block (or one folded in from a real F5
    ledger — see `lib.iterate_tests_block`) satisfies the gate without a
    `no_tests_reason`."""
    monkeypatch.chdir(project)
    monkeypatch.delenv("SHIPWRIGHT_SESSION_ID", raising=False)
    from tools import finalize_iterate as fi

    extras = {
        "intent": "change", "spec_impact": "modify", "affected_frs": ["FR-01.01"],
        "tests": {"passed": 5, "total": 5},
    }
    result = fi.run(project, run_id="test-evidence-allow-002", event_extras=extras)
    assert result["steps"]["event"].get("id") is not None


def test_finalize_rejection_carries_the_triggering_gate_code(project, monkeypatch):
    # Doubt-review finding: main() used to hardcode "fr_gate_unclassified" for
    # every FinalizeGateError regardless of which gate actually fired,
    # mislabeling a missing-evidence rejection on the machine-readable channel.
    monkeypatch.chdir(project)
    monkeypatch.delenv("SHIPWRIGHT_SESSION_ID", raising=False)
    from tools import finalize_iterate as fi

    extras = {"intent": "change", "spec_impact": "modify", "affected_frs": ["FR-01.01"]}
    with pytest.raises(fi.FinalizeGateError) as excinfo:
        fi.run(project, run_id="test-evidence-code-001", event_extras=extras)
    assert excinfo.value.code == "fr_gate_missing_test_evidence"


def test_finalize_malformed_explicit_tests_block_fails_closed(project, monkeypatch):
    # Doubt-review finding: an explicit caller-supplied `tests` block that
    # fails the shared validator raised a bare ValueError inside
    # _fold_tests_block, caught by _record_event's generic `except Exception`
    # and turned into a silently-"skipped" event step — a malformed evidence
    # claim would vanish the whole event behind an apparently successful
    # finalize, bypassing this very gate. Must now fail closed instead.
    monkeypatch.chdir(project)
    monkeypatch.delenv("SHIPWRIGHT_SESSION_ID", raising=False)
    from tools import finalize_iterate as fi

    extras = {
        "intent": "change", "spec_impact": "modify", "affected_frs": ["FR-01.01"],
        "tests": {"passed": 5, "total": 5, "skipped": "n/a"},
    }
    with pytest.raises(fi.FinalizeGateError) as excinfo:
        fi.run(project, run_id="test-evidence-malformed-001", event_extras=extras)
    assert excinfo.value.code == "fr_gate_malformed_tests_block"
    assert [e for e in _read_events_jsonl(project) if e.get("type") == "work_completed"] == []


def test_finalize_docs_only_iterate_needs_no_evidence(project, monkeypatch):
    """spec_impact none (behaviour-preserving) referencing FRs — this run's
    own reconciliation shape — is never gated by this rule. No `tests` key
    here (doubt-review D3-2): with one supplied, the event would already pass
    at the has_test_evidence check and never reach the bypass this test
    claims to pin — omitting it is what makes the assertion able to fail."""
    monkeypatch.chdir(project)
    monkeypatch.delenv("SHIPWRIGHT_SESSION_ID", raising=False)
    from tools import finalize_iterate as fi

    extras = {
        "intent": "change", "spec_impact": "none",
        "spec_impact_justification": "no behavior change, references only",
        "affected_frs": ["FR-01.01"],
    }
    result = fi.run(project, run_id="test-evidence-docs-001", event_extras=extras)
    assert result["steps"]["event"].get("id") is not None
