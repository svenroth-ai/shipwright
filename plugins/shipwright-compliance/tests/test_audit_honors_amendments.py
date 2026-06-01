"""group_d honors event_amended corrections (iterate-2026-06-01-audit-honors-amendments).

The detective audit used to read the event log RAW, so an ``event_amended``
correction was invisible to D1-D5 — unlike the change-history collector, which
already applies amendments. ``group_d.run`` now applies the shared
``apply_amendments`` SSOT before the checks, so a correction is honored
consistently across every compliance surface.
"""

from __future__ import annotations

import json
import sys
import types
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

from scripts.audit import group_d  # noqa: E402


def _events(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def _d5(tmp_path: Path):
    return next(f for f in group_d.run(tmp_path, {}, None) if f.check_id == "D5")


def test_d5_honors_spec_impact_none_amendment(tmp_path):
    # The real-world case: a flagged feature/change event (spec_impact=modify,
    # no FR) corrected by an event_amended that reclassifies spec_impact=none
    # must now PASS D5 (the audit honors the correction).
    _events(tmp_path / "shipwright_events.jsonl", [
        {"id": "evt-1", "type": "work_completed", "source": "iterate",
         "intent": "change", "ts": "2026-06-01T00:00:00+00:00", "commit": "c1",
         "change_type": "fix", "spec_impact": "modify"},
        {"type": "event_amended", "amends": "evt-1",
         "fields": {"spec_impact": "none", "none_reason": "tooling no-op"},
         "ts": "2026-06-01T01:00:00+00:00"},
    ])
    assert _d5(tmp_path).status == "pass"


def test_d5_fails_without_the_amendment(tmp_path):
    # Control: the SAME event without the correction still fails — proving the
    # amendment (not some other quirk) is what flips D5 to pass.
    _events(tmp_path / "shipwright_events.jsonl", [
        {"id": "evt-1", "type": "work_completed", "source": "iterate",
         "intent": "change", "ts": "2026-06-01T00:00:00+00:00", "commit": "c1",
         "change_type": "fix", "spec_impact": "modify"},
    ])
    assert _d5(tmp_path).status == "fail"


def test_d5_honors_affected_frs_amendment(tmp_path):
    # An amendment that ADDS FR linkage also clears D5 (the merge path, not
    # only the spec_impact=none branch).
    _events(tmp_path / "shipwright_events.jsonl", [
        {"id": "evt-2", "type": "work_completed", "source": "iterate",
         "intent": "feature", "ts": "2026-06-01T00:00:00+00:00", "commit": "c2",
         "description": "new cap"},
        {"type": "event_amended", "amends": "evt-2",
         "fields": {"affected_frs": ["FR-001"]}, "ts": "2026-06-01T01:00:00+00:00"},
    ])
    assert _d5(tmp_path).status == "pass"


def test_amended_entry_never_evaluated_as_work_event(tmp_path):
    # The event_amended row itself is dropped, never mistaken for a
    # feature/change work_completed (it carries no intent/spec_impact). With no
    # real work events, D5 skips rather than erroring on the bare amend row.
    _events(tmp_path / "shipwright_events.jsonl", [
        {"type": "event_amended", "amends": "evt-x", "fields": {},
         "ts": "2026-06-01T00:00:00+00:00"},
    ])
    assert _d5(tmp_path).status == "skip"


def test_d2_detects_stale_fr_carried_by_amendment(tmp_path):
    # Post-merge attribution: a stale FR introduced by an amendment rides on
    # the target event after the merge; D2 still flags it. Exercises the exact
    # applier group_d.run() uses (group_d.events_amend.apply_amendments).
    raw = [
        {"id": "evt-3", "type": "work_completed", "source": "iterate",
         "intent": "change", "ts": "2026-06-01T00:00:00+00:00", "commit": "c3",
         "affected_frs": ["FR-001"]},
        {"type": "event_amended", "amends": "evt-3",
         "fields": {"affected_frs": ["FR-999"]}, "ts": "2026-06-01T01:00:00+00:00"},
    ]
    applied = group_d.events_amend.apply_amendments(raw)
    spec_frs = [types.SimpleNamespace(id="FR-001")]
    status, _sev, detail, _evidence = group_d._check_d2(spec_frs, applied)
    assert status == "fail"
    assert "FR-999" in detail
