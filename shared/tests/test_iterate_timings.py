"""Tests for the hierarchical iterate-timing span model (measurement only).

Covers: writers (producer span + agent start/end), resume across separate
process invocations, and the clock-regression fabricated-zero guard.
Hierarchy/normalization tests (parent resolution, exclusive-time,
malformed rejection) live in test_iterate_timings_hierarchy.py — split at
~300 lines per file-size guideline.
"""

from __future__ import annotations

import subprocess
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


# --------------------------------------------------------------------------- #
# record_producer_span_counted — atomic count-then-append
# --------------------------------------------------------------------------- #

def test_record_producer_span_counted_resolves_attempt_1_on_empty_sidecar(tmp_path):
    path, attempt = it.record_producer_span_counted(
        tmp_path, RUN, name="f0_queue", parent="verification",
        start_utc="2026-08-07T10:00:00+00:00", end_utc="2026-08-07T10:00:01+00:00",
        duration_ms=1000, extra={"weight": 1, "capacity": 1},
        count_prior=lambda entries: len(entries))
    assert attempt == 1
    raw = itn.read_raw_events(tmp_path, RUN)
    assert len(raw) == 1
    assert raw[0]["attempt"] == 1
    assert path == it.sidecar_path(tmp_path, RUN)


def test_record_producer_span_counted_passes_tolerant_parsed_prior_entries(tmp_path):
    it.record_producer_span(tmp_path, RUN, name="f0_queue", parent="verification",
                            start_utc="2026-08-07T10:00:00+00:00",
                            end_utc="2026-08-07T10:00:01+00:00", duration_ms=1000)
    seen = {}

    def count_prior(entries):
        seen["entries"] = entries
        return len(entries)

    _, attempt = it.record_producer_span_counted(
        tmp_path, RUN, name="f0_queue", parent="verification",
        start_utc="2026-08-07T10:05:00+00:00", end_utc="2026-08-07T10:05:01+00:00",
        duration_ms=1000, count_prior=count_prior)
    assert attempt == 2
    assert len(seen["entries"]) == 1
    assert seen["entries"][0]["name"] == "f0_queue"


def test_record_producer_span_counted_never_returns_after_a_failed_count(tmp_path):
    def boom(_entries):
        raise ValueError("boom")

    with pytest.raises(ValueError):
        it.record_producer_span_counted(
            tmp_path, RUN, name="f0_queue", parent="verification",
            start_utc="2026-08-07T10:00:00+00:00", end_utc="2026-08-07T10:00:01+00:00",
            duration_ms=1000, count_prior=boom)
    assert itn.read_raw_events(tmp_path, RUN) == []


def test_record_producer_span_counted_rejects_bad_extra_before_writing(tmp_path):
    with pytest.raises(it.IterateTimingError):
        it.record_producer_span_counted(
            tmp_path, RUN, name="f0_queue", parent="verification",
            start_utc="2026-08-07T10:00:00+00:00", end_utc="2026-08-07T10:00:01+00:00",
            duration_ms=1000, extra={"raw_console_output": "nope"},
            count_prior=lambda entries: len(entries))
    assert itn.read_raw_events(tmp_path, RUN) == []


def test_record_producer_span_counted_two_calls_never_collide_same_process(tmp_path):
    """Sequential same-process calls each see the other's durable write —
    the property the F0-specific attempt policy (suite_timing.py) depends
    on when its own process-local cache is cold."""
    _, first = it.record_producer_span_counted(
        tmp_path, RUN, name="f0_queue", parent="verification",
        start_utc="2026-08-07T10:00:00+00:00", end_utc="2026-08-07T10:00:01+00:00",
        duration_ms=1000, count_prior=lambda entries: len(entries))
    _, second = it.record_producer_span_counted(
        tmp_path, RUN, name="f0_queue", parent="verification",
        start_utc="2026-08-07T10:05:00+00:00", end_utc="2026-08-07T10:05:01+00:00",
        duration_ms=1000, count_prior=lambda entries: len(entries))
    assert first == 1
    assert second == 2


def test_record_producer_span_counted_serializes_across_real_OS_processes(tmp_path):
    """External code review (Branch A architecture-mode follow-up, plan
    review round 4): the same-process test above proves the lock serializes
    within one interpreter, but record_producer_span_counted's own docstring
    claims atomicity specifically across separate OS processes — the exact
    property record_producer_span's FileLock already has a subprocess proof
    for (test_iterate_timings_concurrency.py). This is that proof for the
    counted resolver: N real `python -c` subprocesses race to
    count-then-append against the SAME sidecar; every one must resolve to a
    distinct attempt, never a duplicate — a duplicate would mean two
    processes read the same prior count before either had written.

    A second external-review pass (over this exact test) flagged that with
    no deliberate delay, the read-count-append critical section is so fast
    that even a BROKEN lock could pass by luck of OS scheduling alone — not
    a reliable proof. `count_prior` here sleeps AFTER the read (inside the
    section the lock is supposed to hold exclusively): with a working lock
    every process serializes through that sleep one at a time and still
    produces {1..N}; with a broken one, multiple processes would overlap
    inside the sleep, read the same prior count, and collide deterministically
    rather than by chance."""
    n = 6
    write_one = (
        "import sys; sys.path.insert(0, {scripts!r}); "
        "from lib import iterate_timings as it; "
        "it.record_producer_span_counted({root!r}, {run!r}, name='f0_queue', "
        "parent='verification', start_utc='2026-08-07T10:00:00+00:00', "
        "end_utc='2026-08-07T10:00:01+00:00', duration_ms=1000, "
        "count_prior=lambda entries: __import__('time').sleep(0.05) or len(entries))"
    )
    procs = [
        subprocess.Popen([sys.executable, "-c", write_one.format(
            scripts=str(_SCRIPTS), root=str(tmp_path), run=RUN)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        for _ in range(n)
    ]
    for p in procs:
        _, stderr = p.communicate(timeout=30)
        assert p.returncode == 0, stderr

    raw = itn.read_raw_events(tmp_path, RUN)
    assert len(raw) == n
    assert {e["attempt"] for e in raw} == set(range(1, n + 1))


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
