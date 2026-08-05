"""Pure ``run_stat()`` computation tests — no report I/O.

Split from ``test_iterate_throughput_report.py`` at ~300 lines (mirrors the
``iterate_throughput_stats.py`` / ``iterate_throughput_report.py`` module
split). Covers exclusive-time union correctness, duplicate top-level span
selection, fold-time-capturable coverage, and the covered/total envelope
invariant.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(_SCRIPTS))

from lib.iterate_throughput_stats import run_stat  # noqa: E402


def test_unattributed_never_goes_negative_when_top_level_branches_overlap():
    """An agent that forgot to close 'planning' before opening 'implementation'
    leaves two top-level branches overlapping in wall-clock terms — summing
    exclusive_ms across both would double-count the overlap and could drive
    unattributed_ms negative (external plan review, round 2). The union-based
    calculation must stay >= 0 and never exceed the measured envelope."""
    event = {"type": "work_completed", "source": "iterate", "adr_id": "r", "ts": "x", "iterate_timings": [
        {"name": "planning", "parent": None, "source": "agent", "outcome": "completed",
         "start_utc": "2026-08-04T09:00:00+00:00", "end_utc": "2026-08-04T09:30:00+00:00",
         "duration_ms": 1800000, "exclusive_ms": 1800000, "attempt": 1, "extra": {}},
        # implementation starts BEFORE planning's own end_utc — overlap.
        {"name": "implementation", "parent": None, "source": "agent", "outcome": "completed",
         "start_utc": "2026-08-04T09:20:00+00:00", "end_utc": "2026-08-04T10:00:00+00:00",
         "duration_ms": 2400000, "exclusive_ms": 2400000, "attempt": 1, "extra": {}},
    ]}
    stat = run_stat(event)
    assert stat["unattributed_ms"] >= 0
    assert stat["unattributed_ms"] <= stat["total_ms"]
    # union of [09:00,09:30] and [09:20,10:00] = 60 minutes; total envelope
    # (earliest start to latest end) is also exactly 60 minutes here, so
    # nothing is unattributed — NOT the naive-sum answer (which would have
    # summed 30+40=70 minutes of "exclusive" time against a 60-minute total,
    # driving this negative before the max(0, ...) clamp masked it).
    assert stat["unattributed_ms"] == 0


def test_duplicate_top_level_span_picks_the_producer_not_insertion_order():
    """Code review finding: a bare dict-comprehension keyed by name silently
    kept whichever of two same-named top-level spans sorted last, which could
    be the shorter/less-accurate agent mark instead of the fuller producer
    span (e.g. a redundant agent 'start delivery' alongside deliver_pr.py's
    own self-recorded one). The producer instance must win regardless of
    which one appears later in the list."""
    event = {"type": "work_completed", "source": "iterate", "adr_id": "r", "ts": "x", "iterate_timings": [
        # The agent's redundant mark is INCOMPLETE and sorts LAST (its start
        # is later) — a naive "last wins" dict comprehension would pick this
        # shorter, still-open instance over the real producer span below.
        {"name": "delivery", "parent": None, "source": "agent", "outcome": "incomplete",
         "start_utc": "2026-08-04T10:05:00+00:00", "end_utc": None,
         "duration_ms": None, "exclusive_ms": None, "attempt": 1, "extra": {}},
        {"name": "delivery", "parent": None, "source": "producer", "outcome": "completed",
         "start_utc": "2026-08-04T10:00:00+00:00", "end_utc": "2026-08-04T10:30:00+00:00",
         "duration_ms": 1800000, "exclusive_ms": 1800000, "attempt": 1, "extra": {}},
    ]}
    stat = run_stat(event)
    assert stat["phases"]["delivery"]["present"] is True
    assert stat["phases"]["delivery"]["outcome"] == "completed"
    assert stat["phases"]["delivery"]["duration_ms"] == 1800000
    assert stat["total_ms"] == 1800000


def test_a_fully_covered_pre_fold_run_reads_as_not_degraded():
    """Doubt review: finalization's own duration and the entire delivery
    group structurally can never close (or, for delivery, never even exist)
    by F5b fold time in ANY run — measuring 'degraded' against all 7 groups
    would pin every real run to permanently DEGRADED, with zero
    discriminating power. A run where all 5 fold-time-capturable groups
    (discovery_diagnosis/planning/implementation/verification/review) closed
    cleanly must read as NOT degraded, even though finalization/delivery are
    (correctly, structurally) absent."""
    t0 = "2026-08-04T09:00:00+00:00"
    spans = []
    names = ("discovery_diagnosis", "planning", "implementation", "verification", "review")
    for i, name in enumerate(names):
        spans.append({
            "name": name, "parent": None, "source": "agent", "outcome": "completed",
            "start_utc": f"2026-08-04T{9 + i:02d}:00:00+00:00",
            "end_utc": f"2026-08-04T{10 + i:02d}:00:00+00:00",
            "duration_ms": 3600000, "exclusive_ms": 3600000, "attempt": 1, "extra": {},
        })
    # finalization: started (per the SKILL's F1 mark) but never closed at
    # fold time — present, but must not count against coverage.
    spans.append({
        "name": "finalization", "parent": None, "source": "agent", "outcome": "incomplete",
        "start_utc": f"2026-08-04T{9 + len(names):02d}:00:00+00:00", "end_utc": None,
        "duration_ms": None, "exclusive_ms": None, "attempt": 1, "extra": {},
    })
    event = {"type": "work_completed", "source": "iterate", "adr_id": "r", "ts": t0,
            "iterate_timings": spans}
    stat = run_stat(event)
    assert stat["coverage_top_level"] == 5
    assert stat["coverage_top_level_total"] == 5
    assert stat["degraded"] is False
    assert stat["phases"]["finalization"]["present"] is True  # still shown
    assert stat["phases"]["delivery"]["present"] is False


def test_covered_ms_never_exceeds_the_selected_envelope():
    """External code review: total_ms is built only from _select_top_level's
    chosen representatives, but the union for unattributed_ms used to scan
    ALL spans in the event — including a discarded duplicate top-level
    instance whose own interval falls outside the selected envelope. Without
    clipping, covered_ms could exceed total_ms and silently clamp
    unattributed_ms to 0 even when a real gap exists."""
    event = {"type": "work_completed", "source": "iterate", "adr_id": "r", "ts": "x", "iterate_timings": [
        # Selected representative: producer, narrow [10:00, 10:10] (10 min).
        {"name": "delivery", "parent": None, "source": "producer", "outcome": "completed",
         "start_utc": "2026-08-04T10:00:00+00:00", "end_utc": "2026-08-04T10:10:00+00:00",
         "duration_ms": 600000, "exclusive_ms": 600000, "attempt": 1, "extra": {}},
        # Discarded duplicate: agent, WIDER [09:00, 11:00] (2h) — loses
        # _select_top_level's producer-over-agent tiebreak, but is still
        # present in `spans` and must not inflate covered_ms past total_ms.
        {"name": "delivery", "parent": None, "source": "agent", "outcome": "completed",
         "start_utc": "2026-08-04T09:00:00+00:00", "end_utc": "2026-08-04T11:00:00+00:00",
         "duration_ms": 7200000, "exclusive_ms": 7200000, "attempt": 1, "extra": {}},
    ]}
    stat = run_stat(event)
    assert stat["total_ms"] == 600000  # from the SELECTED (producer) representative only
    assert stat["unattributed_ms"] == 0
    assert stat["unattributed_ms"] <= stat["total_ms"]


def test_present_but_incomplete_top_level_span_does_not_count_toward_coverage():
    """External code review: presence alone is not coverage — a span that is
    'present' with outcome incomplete/unavailable or no duration_ms must not
    count toward coverage_top_level, or a run of bare start marks would read
    as fully covered."""
    event = {"type": "work_completed", "source": "iterate", "adr_id": "r", "ts": "x", "iterate_timings": [
        {"name": "planning", "parent": None, "source": "agent", "outcome": "incomplete",
         "start_utc": "2026-08-04T09:00:00+00:00", "end_utc": None,
         "duration_ms": None, "exclusive_ms": None, "attempt": 1, "extra": {}},
    ]}
    stat = run_stat(event)
    assert stat["phases"]["planning"]["present"] is True
    assert stat["coverage_top_level"] == 0
    assert stat["degraded"] is True
