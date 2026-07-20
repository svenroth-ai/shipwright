"""Record-boundary recovery at the SHARED-context remainder readers + validator.

Part 2 of iterate-2026-07-19-events-record-boundary-readers (which fixed 11 sites
and filed the rest as ``trg-360e494f``). This module pins the three sites that
live in a shared-import context — ``phase_quality._resolution.resolve_run_id``,
``verifiers.adopt_compliance.check_a7_adopted_event``, and
``churn_merge.validate_events_text`` — all of which open-coded "one line == one
record" and so discarded EVERY record on a physical line holding two.

The input is built exactly as a ``merge=union`` merge propagates it: two valid
records joined on one physical line (``json.dumps(A) + json.dumps(B)``), no crash
or interrupted write required. The plugin-side siblings (grade ``routing`` and
adopt ``validate_adoption``) are pinned in their own plugin test suites; the
end-to-end composition over a real git merge is
``integration-tests/test_events_record_boundary_merge_integration.py``.
"""
from __future__ import annotations

import json
import warnings
from pathlib import Path

from lib import phase_quality as pq
from lib.churn_merge import validate_events_text
from lib.phase_quality import STATUS_FAIL, STATUS_PASS
from tools.verifiers.adopt_compliance import check_a7_adopted_event


def _write_events(root: Path, text: str) -> None:
    (root / "shipwright_events.jsonl").write_text(text, encoding="utf-8")


# ---------------------------------------------------------------------------
# AC1 — resolve_run_id: recover run_started records from a concatenated line
# ---------------------------------------------------------------------------

def test_resolve_run_id_recovers_run_started_from_a_concatenated_line(tmp_path: Path) -> None:
    """Pre-fix the concatenated line was skipped whole, so run-id resolution fell
    through to the session-id fallback — silently mis-attributing every audit row
    that keys on the resolved run to the wrong id."""
    a = {"type": "run_started", "run_id": "iterate-aaa"}
    b = {"type": "run_started", "run_id": "iterate-bbb"}
    _write_events(tmp_path, json.dumps(a) + json.dumps(b) + "\n")
    # Latest-wins: b is second in wire order, so its run_id is the resolved one.
    assert pq.resolve_run_id(tmp_path, "sess-fallback") == "iterate-bbb"


def test_resolve_run_id_skips_a_fragment_and_keeps_what_decoded(tmp_path: Path) -> None:
    """Partial recovery, never all-or-nothing: a valid record ahead of an
    unrecoverable fragment still resolves."""
    a = {"type": "run_started", "run_id": "iterate-aaa"}
    _write_events(tmp_path, json.dumps(a) + "{truncated\n")
    assert pq.resolve_run_id(tmp_path, "sess-fallback") == "iterate-aaa"


def test_resolve_run_id_still_falls_back_when_log_absent(tmp_path: Path) -> None:
    """The documented fallback chain must survive the delegation."""
    assert pq.resolve_run_id(tmp_path, "sess-fallback") == "sess-fallback"


# ---------------------------------------------------------------------------
# AC2 / AC5 / AC6 — check_a7_adopted_event: the INVERTED failure mode
# ---------------------------------------------------------------------------

def test_check_a7_counts_adopted_when_it_is_second_on_a_concatenated_line(tmp_path: Path) -> None:
    """The operator-facing inversion: a correctly-adopted repo whose ``adopted``
    event is the SECOND record on a concatenated line read as NOT adopted, so A7
    FAILed a repo that had adopted correctly. Post-fix it PASSes."""
    other = {"type": "phase_completed", "id": "e1"}
    adopted = {"type": "adopted", "id": "e2"}
    _write_events(tmp_path, json.dumps(other) + json.dumps(adopted) + "\n")
    assert check_a7_adopted_event(tmp_path)["status"] == STATUS_PASS


def test_check_a7_still_fails_when_adopted_genuinely_absent(tmp_path: Path) -> None:
    """Anti-vacuity: recovery must not make the gate pass on a real absence."""
    _write_events(tmp_path, json.dumps({"type": "phase_completed", "id": "e1"}) + "\n")
    assert check_a7_adopted_event(tmp_path)["status"] == STATUS_FAIL


def test_check_a7_does_not_crash_on_a_bare_scalar_line(tmp_path: Path) -> None:
    """AC6: pre-fix ``json.loads('5')`` -> int, then ``5.get('type')`` raised
    AttributeError (a latent crash the delegation removes). The scalar is a
    fragment; the real ``adopted`` record is still counted."""
    _write_events(tmp_path, "5\n" + json.dumps({"type": "adopted", "id": "e2"}) + "\n")
    assert check_a7_adopted_event(tmp_path)["status"] == STATUS_PASS


# ---------------------------------------------------------------------------
# AC-CM1 / AC-CM2 — churn_merge.validate_events_text
# ---------------------------------------------------------------------------

def test_validate_events_text_finds_work_completed_second_on_a_concatenated_line(tmp_path: Path) -> None:
    """AC-CM1: the false ``check_events_has_commit`` failure during
    ``integrate_main``. Pre-fix, a ``work_completed`` sitting second on a
    concatenated line never matched ``require_run_id`` AND the line was reported
    as 'not valid JSON' — two false errors for a correctly-recorded run."""
    other = {"type": "phase_completed", "id": "e1"}
    work = {"type": "work_completed", "adr_id": "iterate-x", "id": "e2"}
    text = json.dumps(other) + json.dumps(work) + "\n"
    assert validate_events_text(text, require_run_id="iterate-x") == []


def test_validate_events_text_does_not_flag_a_recoverable_concatenated_line(tmp_path: Path) -> None:
    """AC-CM2 (the pinned reporting change): a fully-recoverable concatenation of
    two valid records is a union artefact, NOT corruption, so it is no longer
    reported as 'not valid JSON'."""
    text = json.dumps({"ok": 1}) + json.dumps({"ok": 2}) + "\n"
    assert validate_events_text(text) == []


def test_validate_events_text_still_flags_a_genuinely_unrecoverable_fragment(tmp_path: Path) -> None:
    """AC-CM2, the other half: check (a) is preserved. A valid record followed by
    an undecodable tail still yields the corruption error for the fragment."""
    errs = validate_events_text(json.dumps({"ok": 1}) + "{truncated\n")
    assert any("not valid JSON" in e for e in errs)


def test_validate_events_text_flags_a_bare_scalar_line_as_corrupt(tmp_path: Path) -> None:
    """The one deliberate divergence (external review, OpenAI #3): a lone scalar
    line is not a valid event record, so the object-only SSoT treats it as a
    fragment and it is reported. The pre-fix per-line ``json.loads`` accepted it
    silently (a scalar IS valid JSON). Consistent with the predecessor's AC12
    (``change_history`` warns for a bare scalar) — enumerated, not incidental. A
    scalar line never occurs on a real event log, so this cannot manufacture a
    false ``integrate_main`` failure."""
    errs = validate_events_text("5\n")
    assert any("not valid JSON" in e for e in errs)


def test_validate_events_text_still_reports_absent_run_event(tmp_path: Path) -> None:
    """Anti-vacuity for the validator: a genuinely absent ``work_completed`` for
    the run id still fails (the gate is not made toothless by recovery)."""
    text = json.dumps({"type": "phase_completed", "id": "e1"}) + "\n"
    assert validate_events_text(text, require_run_id="iterate-x")


def test_recovery_is_silent(tmp_path: Path) -> None:
    """Governing invariant: behaviour-preserving except record recovery. None of
    these shared readers emit a warning (the SSoT returns corruption as data)."""
    other = {"type": "phase_completed", "id": "e1"}
    adopted = {"type": "adopted", "id": "e2"}
    _write_events(tmp_path, json.dumps(other) + json.dumps(adopted) + "\n")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        check_a7_adopted_event(tmp_path)
        pq.resolve_run_id(tmp_path, "sess")
        validate_events_text(json.dumps(other) + json.dumps(adopted) + "\n")
    assert caught == [], f"remainder readers must stay silent, emitted: {[str(w.message) for w in caught]}"
