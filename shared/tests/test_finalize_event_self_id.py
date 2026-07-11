"""Tests for the campaign event self-identification stamp (S1).

Campaign 2026-06-07-tracked-campaign-status, sub-iterate S1: a campaign
sub-iterate's F5b finalize passes ``--event-extras-json`` carrying
``campaign`` + ``sub_iterate_id``, so the ``work_completed`` event in
``shipwright_events.jsonl`` is self-sufficient — per-sub status can be
projected from the log (S2) without the unreliable slug-join heuristic.

Pins the three S1 acceptance criteria against the REAL producer
(``finalize_iterate.run`` / ``main``), not a mock. Split out of
``test_finalize_iterate.py`` (baseline-frozen at its current LOC).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

_CAMPAIGN = "2026-06-07-tracked-campaign-status"

# FR-gate-valid classification + the S1 identity stamp.
_STAMPED_EXTRAS = {
    "change_type": "tooling",
    "none_reason": "campaign stamp unit test",
    "campaign": _CAMPAIGN,
    "sub_iterate_id": "S1",
}


def _import_finalize():
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    from tools import finalize_iterate as fi
    return fi


@pytest.fixture()
def project(tmp_path):
    """Minimal project layout (mirrors test_finalize_iterate.py)."""
    (tmp_path / "shipwright_run_config.json").write_text(
        json.dumps({"status": "complete", "iterate_history": []}),
        encoding="utf-8",
    )
    (tmp_path / ".shipwright" / "agent_docs").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".shipwright" / "compliance").mkdir(parents=True)
    (tmp_path / "shipwright_events.jsonl").write_text("", encoding="utf-8")
    return tmp_path


def _events(project: Path) -> list[dict]:
    raw = (project / "shipwright_events.jsonl").read_text(encoding="utf-8")
    return [json.loads(line) for line in raw.splitlines() if line.strip()]


def test_event_carries_campaign_and_sub_iterate_id(project, monkeypatch):
    """AC-1: work_completed carries extras.campaign + extras.sub_iterate_id."""
    monkeypatch.chdir(project)
    monkeypatch.delenv("SHIPWRIGHT_SESSION_ID", raising=False)
    fi = _import_finalize()

    result = fi.run(project, run_id="iterate-s1-stamp-001",
                    event_extras=dict(_STAMPED_EXTRAS))
    assert result["steps"]["event"].get("id") is not None

    [event] = [e for e in _events(project) if e["type"] == "work_completed"]
    assert event["type"] == "work_completed"
    assert event["source"] == "iterate"
    assert event["campaign"] == _CAMPAIGN
    assert event["sub_iterate_id"] == "S1"


def test_stamp_is_idempotent_per_run_id(project, monkeypatch):
    """AC-2: a finalize re-run with the same run_id returns the existing
    event id and does NOT append a second (stamped) event line."""
    monkeypatch.chdir(project)
    monkeypatch.delenv("SHIPWRIGHT_SESSION_ID", raising=False)
    fi = _import_finalize()

    first = fi.run(project, run_id="iterate-s1-stamp-002",
                   event_extras=dict(_STAMPED_EXTRAS))
    second = fi.run(project, run_id="iterate-s1-stamp-002",
                    event_extras=dict(_STAMPED_EXTRAS))

    assert second["steps"]["event"]["id"] == first["steps"]["event"]["id"]
    events = [e for e in _events(project) if e["type"] == "work_completed"]
    assert len(events) == 1
    assert events[0]["campaign"] == _CAMPAIGN
    assert events[0]["sub_iterate_id"] == "S1"


def test_cli_manual_flag_path_stamps_event(project, monkeypatch):
    """AC-3: the manual ``/shipwright-iterate --campaign <slug>
    --sub-iterate-id <id>`` path materializes as ``--event-extras-json``
    on the finalize CLI — the stamp reaches the event, exit code 0."""
    monkeypatch.chdir(project)
    monkeypatch.delenv("SHIPWRIGHT_SESSION_ID", raising=False)
    fi = _import_finalize()

    rc = fi.main([
        "--project-root", str(project),
        "--run-id", "iterate-s1-stamp-cli-001",
        "--reason", "iterate: manual campaign sub-iterate",
        "--event-extras-json", json.dumps(_STAMPED_EXTRAS),
    ])
    assert rc == 0

    [event] = [e for e in _events(project) if e["type"] == "work_completed"]
    assert event["campaign"] == _CAMPAIGN
    assert event["sub_iterate_id"] == "S1"
    assert event["adr_id"] == "iterate-s1-stamp-cli-001"


def test_stamp_does_not_bypass_fr_gate(project, monkeypatch):
    """Boundary pin: the stamp keys are additive metadata, NOT a
    classification — an otherwise-unclassified event still fails the
    FR-gate even when campaign/sub_iterate_id are present."""
    monkeypatch.chdir(project)
    monkeypatch.delenv("SHIPWRIGHT_SESSION_ID", raising=False)
    fi = _import_finalize()

    unclassified = {"campaign": _CAMPAIGN, "sub_iterate_id": "S1"}
    with pytest.raises(fi.FinalizeGateError):
        fi.run(project, run_id="iterate-s1-stamp-gate-001",
               event_extras=unclassified)
    assert [e for e in _events(project)
            if e.get("type") == "work_completed"] == []
