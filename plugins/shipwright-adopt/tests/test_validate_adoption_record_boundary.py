"""Record-boundary recovery for adopt's ``_validate_events`` soft check.

``validate_adoption._validate_events`` counts the single ``adopted`` event. Like
its verifier sibling ``adopt_compliance.check_a7_adopted_event`` it parsed one
physical line at a time, so an ``adopted`` event sitting second on a concatenated
line (the artefact a ``merge=union`` merge propagates) read as absent — the
inverted failure mode where a correctly-adopted repo reports "no 'adopted' event".

Part 2 of iterate-2026-07-19-events-record-boundary-readers (filed as
``trg-360e494f``). ``validate_adoption`` ships inside adopt's own ``scripts``, so
the shared SSoT is loaded by file location under a sentinel (the ADR-045 barrier),
mirroring the module's existing ``_discovery()`` helper.
"""
from __future__ import annotations

import json
from pathlib import Path

from checks.validate_adoption import _validate_events


def _write_events(root: Path, text: str) -> None:
    (root / "shipwright_events.jsonl").write_text(text, encoding="utf-8")


def test_validate_events_recovers_adopted_second_on_a_concatenated_line(tmp_path: Path) -> None:
    """Pre-fix the concatenated line was skipped whole, so a correctly-adopted
    repo reported 'no adopted event found'. Post-fix the event is recovered."""
    other = {"type": "phase_completed"}
    adopted = {"type": "adopted"}
    _write_events(tmp_path, json.dumps(other) + json.dumps(adopted) + "\n")
    assert _validate_events(tmp_path) == []


def test_validate_events_partial_recovery_keeps_the_adopted_record(tmp_path: Path) -> None:
    """Partial recovery, never all-or-nothing."""
    adopted = {"type": "adopted"}
    _write_events(tmp_path, json.dumps(adopted) + "{truncated\n")
    assert _validate_events(tmp_path) == []


def test_validate_events_still_fails_when_adopted_absent(tmp_path: Path) -> None:
    """Anti-vacuity: a genuinely absent ``adopted`` event still errors."""
    _write_events(tmp_path, json.dumps({"type": "phase_completed"}) + "\n")
    errs = _validate_events(tmp_path)
    assert errs and any("adopted" in e for e in errs)


def test_validate_events_does_not_crash_on_a_bare_scalar_line(tmp_path: Path) -> None:
    """A scalar line is a fragment, not a record — no ``.get`` crash, and the real
    ``adopted`` event is still counted."""
    _write_events(tmp_path, "5\n" + json.dumps({"type": "adopted"}) + "\n")
    assert _validate_events(tmp_path) == []
