"""Tests for the hierarchical iterate-timing span model (measurement only).

Covers: writers (producer span + agent start/end), resume across separate
process invocations, and the clock-regression fabricated-zero guard.
Hierarchy/normalization tests (parent resolution, exclusive-time,
malformed rejection) live in test_iterate_timings_hierarchy.py — split at
~300 lines per file-size guideline.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(_SCRIPTS))

from lib import iterate_timings as it  # noqa: E402
from lib import iterate_timings_normalize as itn  # noqa: E402

RUN = "iterate-2026-08-04-iterate-timing-attribution"


# --------------------------------------------------------------------------- #
# Writers
# --------------------------------------------------------------------------- #

def test_record_producer_span_rejects_unknown_name(tmp_path):
    with pytest.raises(it.IterateTimingError):
        it.record_producer_span(tmp_path, RUN, name="not-a-real-span", parent=None,
                                start_utc="2026-08-04T10:00:00+00:00",
                                end_utc="2026-08-04T10:00:01+00:00", duration_ms=1000)


def test_record_producer_span_rejects_wrong_parent(tmp_path):
    with pytest.raises(it.IterateTimingError):
        it.record_producer_span(tmp_path, RUN, name="f0_queue", parent="review",
                                start_utc="2026-08-04T10:00:00+00:00",
                                end_utc="2026-08-04T10:00:01+00:00", duration_ms=1000)


def test_record_end_rejects_unclosed_vocabulary_extra(tmp_path):
    with pytest.raises(it.IterateTimingError):
        it.record_end(tmp_path, RUN, name="review", parent=None,
                      extra={"raw_console_output": "whatever"})


def test_span_context_manager_records_on_success(tmp_path):
    with it.span(tmp_path, RUN, name="pre_f0_validation", parent="verification") as extra:
        extra["stage"] = "f0"
    raw = itn.read_raw_events(tmp_path, RUN)
    assert len(raw) == 1
    assert raw[0]["event"] == "span"
    assert raw[0]["outcome"] == "completed"
    assert raw[0]["extra"] == {"stage": "f0"}


def _boom() -> None:
    raise ValueError("boom")


def test_span_context_manager_marks_incomplete_on_exception(tmp_path):
    # A CALLED helper, not an inline `raise`, keeps CodeQL's Python CFG
    # analysis (py/unreachable-statement) from mis-modeling the code after
    # this `with pytest.raises(...)` block as unreachable — it does not
    # account for pytest.raises() catching the exception, only for a `try`/
    # `except` it can see directly (false positive: this code IS reached).
    with pytest.raises(ValueError):
        with it.span(tmp_path, RUN, name="pre_f0_validation", parent="verification"):
            _boom()
    raw = itn.read_raw_events(tmp_path, RUN)
    assert raw[0]["outcome"] == "incomplete"


def test_sidecar_is_append_only_across_sequential_calls(tmp_path):
    """The writers hold no in-memory state — each call only reads/appends the
    file — so a second call sees everything an earlier one wrote purely
    through the sidecar, the same property a resumed OS process would rely
    on. This test makes two calls in the SAME Python process to isolate that
    property cheaply; a genuine cross-OS-process resume is proven separately
    by test_iterate_timing_cli.py::test_resume_across_real_separate_os_processes
    (external code review: a same-process test claiming "separate process
    invocations" over-states what it verifies)."""
    it.record_start(tmp_path, RUN, name="planning", parent=None)
    raw_first = itn.read_raw_events(tmp_path, RUN)
    assert len(raw_first) == 1

    it.record_end(tmp_path, RUN, name="planning", parent=None)
    raw_second = itn.read_raw_events(tmp_path, RUN)
    assert len(raw_second) == 2
    valid, rejected = itn.normalize_iterate_timings(raw_second)
    assert not rejected
    assert valid[0]["name"] == "planning" and valid[0]["outcome"] == "completed"


def test_clock_regression_between_marks_never_fabricates_a_zero(tmp_path):
    """Doubt review: a wall-clock step-back between two separate CLI
    invocations (NTP correction, suspend/resume) must not silently clamp to
    a fabricated 0ms 'completed' span — the exact outcome the card's own
    acceptance criteria forbid."""
    it.record_start(tmp_path, RUN, name="planning", parent=None,
                    ts="2026-08-04T10:05:00+00:00")
    # end's wall-clock timestamp is BEFORE start's — a real clock regression.
    it.record_end(tmp_path, RUN, name="planning", parent=None,
                  ts="2026-08-04T10:00:00+00:00")
    valid, rejected = itn.normalize_iterate_timings(itn.read_raw_events(tmp_path, RUN))
    assert not rejected
    planning = next(v for v in valid if v["name"] == "planning")
    assert planning["outcome"] == "unavailable"
    assert planning["duration_ms"] is None
    assert planning["exclusive_ms"] is None
    assert planning["end_utc"] is None  # untrustworthy end dropped, not kept
