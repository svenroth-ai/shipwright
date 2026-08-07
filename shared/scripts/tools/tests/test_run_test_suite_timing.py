"""F0 producer timing: f0_queue vs canonical_f0_active attribution.

``record_f0_queue_span`` persists what ``host_resource_lease.LeaseGrant.
waited_seconds`` already computes and today discards — this pins that it is
recorded correctly, gated to canonical iterate run_ids, and never raises.
Lives in ``suite_timing.py`` (split from ``run_test_suite.py`` per ADR-123's
addendum); ``run_test_suite.py`` only calls it, and is not re-tested here.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

import scripts.lib.iterate_timings_normalize as itn
import scripts.tools.suite_timing as mod

RUN = "iterate-2026-08-04-iterate-timing-attribution"

# Attempt auto-numbering, per-unit f0_unit_result emission, and the
# import-path landmine probe (test-phase-attribution) live in the sibling
# test_run_test_suite_attempt_attribution.py, split out at the ~300-line
# file-size guideline.


def test_f0_queue_span_recorded_for_canonical_run_id(tmp_path):
    mod.record_f0_queue_span(tmp_path, RUN, waited_seconds=1080.0, weight=22, capacity=22,
                             stage="cpu")
    raw = itn.read_raw_events(tmp_path, RUN)
    assert len(raw) == 1
    assert raw[0]["name"] == "f0_queue"
    assert raw[0]["duration_ms"] == 1080000
    assert raw[0]["extra"] == {"weight": 22, "capacity": 22, "stage": "cpu"}
    assert raw[0]["attempt"] == 1


def test_f0_queue_span_skipped_for_non_canonical_run_id(tmp_path):
    mod.record_f0_queue_span(tmp_path, "f0-ad-hoc-probe", waited_seconds=5.0,
                             weight=1, capacity=1, stage="cpu")
    assert itn.read_raw_events(tmp_path, "f0-ad-hoc-probe") == []


def test_f0_queue_span_skipped_for_a_run_id_that_only_LOOKS_canonical(tmp_path):
    """External code review: a bare ``.startswith("iterate-")`` check also
    matches a malformed id missing the date component — RUN_ID_STRICT (the
    same regex ``iterate_timing.py``'s own CLI enforces) is what must gate
    this, not a loose prefix."""
    mod.record_f0_queue_span(tmp_path, "iterate-not-canonical", waited_seconds=5.0,
                             weight=1, capacity=1, stage="cpu")
    assert itn.read_raw_events(tmp_path, "iterate-not-canonical") == []


def test_f0_queue_span_skipped_when_no_wait_occurred(tmp_path):
    """Zero wait is not a span worth recording — avoids a flood of 0ms entries
    on every F0 run where nothing was ever queued."""
    mod.record_f0_queue_span(tmp_path, RUN, waited_seconds=0.0, weight=1, capacity=1,
                             stage="cpu")
    assert itn.read_raw_events(tmp_path, RUN) == []


def test_f0_queue_span_never_raises_on_bad_project_root():
    """Best-effort: an unwritable/invalid root must not fail F0 itself."""
    mod.record_f0_queue_span(Path("\0invalid"), RUN, waited_seconds=5.0, weight=1, capacity=1,
                             stage="cpu")


def test_canonical_f0_active_span_recorded_from_the_real_result_shape(tmp_path):
    """Regression: the field is SuiteResult.seconds, not .duration — a prior
    version of this call read a nonexistent attribute and was silently
    swallowed by the best-effort guard on every real F0 run."""
    result = SimpleNamespace(seconds=324.0)
    start = datetime(2026, 8, 4, 10, 18, 2, tzinfo=timezone.utc)
    mod.record_canonical_f0_active_span(tmp_path, RUN, active_start=start, result=result,
                                        weight=22, capacity=22)
    raw = itn.read_raw_events(tmp_path, RUN)
    assert len(raw) == 1
    assert raw[0]["name"] == "canonical_f0_active"
    assert raw[0]["duration_ms"] == 324000


def test_canonical_f0_active_span_never_raises_when_result_lacks_seconds(tmp_path):
    """A caller or test double whose ``result`` doesn't shape-match must
    degrade to a skipped span, never propagate — the attribute read has to
    stay INSIDE the best-effort guard, not move to the call site."""
    start = datetime(2026, 8, 4, 10, 18, 2, tzinfo=timezone.utc)
    mod.record_canonical_f0_active_span(tmp_path, RUN, active_start=start, result="not-a-result",
                                        weight=1, capacity=1)
    assert itn.read_raw_events(tmp_path, RUN) == []


def test_canonical_f0_active_span_failed_records_incomplete(tmp_path):
    """External code review: a `run_suite()` that raises before returning must
    still leave a producer boundary — exactly the run where attribution
    matters most — instead of silently losing the span."""
    start = datetime(2026, 8, 4, 10, 18, 2, tzinfo=timezone.utc)
    mod.record_canonical_f0_active_span_failed(tmp_path, RUN, active_start=start,
                                                weight=22, capacity=22)
    raw = itn.read_raw_events(tmp_path, RUN)
    assert len(raw) == 1
    assert raw[0]["name"] == "canonical_f0_active"
    assert raw[0]["outcome"] == "incomplete"
    assert raw[0]["duration_ms"] is not None and raw[0]["duration_ms"] >= 0


def test_canonical_f0_active_span_failed_skipped_for_non_canonical_run_id(tmp_path):
    start = datetime(2026, 8, 4, 10, 18, 2, tzinfo=timezone.utc)
    mod.record_canonical_f0_active_span_failed(tmp_path, "f0-ad-hoc-probe", active_start=start,
                                                weight=1, capacity=1)
    assert itn.read_raw_events(tmp_path, "f0-ad-hoc-probe") == []
