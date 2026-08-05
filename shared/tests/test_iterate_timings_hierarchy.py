"""Hierarchy normalization tests for iterate-timing spans (measurement only).

Covers: parent resolution (containment, tiebreaks, cascade rejection),
overlap/exclusive-time computation, malformed-entry rejection (per-entry,
not all-or-nothing), and the synthetic weight-22 F0 blocker case (P1.16).
Split from test_iterate_timings.py at ~300 lines; missing-ancestor synthesis
(the absent-name case) is its own further split, test_iterate_timings_synthesis.py.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(_SCRIPTS))

from lib import iterate_timings as it  # noqa: E402
from lib import iterate_timings_normalize as itn  # noqa: E402

RUN = "iterate-2026-08-04-iterate-timing-attribution"


def _span(name, parent, start, end, duration_ms, **extra):
    return {"event": "span", "name": name, "parent": parent, "attempt": 1,
           "source": "producer", "outcome": "completed", "start_utc": start,
           "end_utc": end, "duration_ms": duration_ms, "extra": extra}


def test_malformed_entry_is_dropped_without_voiding_the_run(tmp_path):
    """The core fix this card exists for: one bad line must not zero the run."""
    raw = [
        _span("review", None, "2026-08-04T10:00:00+00:00", "2026-08-04T10:10:00+00:00", 600000),
        {"event": "span", "name": "totally-bogus", "parent": None, "start_utc": "x",
         "end_utc": None, "duration_ms": -1, "attempt": 1, "source": "producer",
         "outcome": "completed", "extra": {}},
    ]
    valid, rejected = itn.normalize_iterate_timings(raw)
    assert len(valid) == 1 and valid[0]["name"] == "review"
    assert len(rejected) == 1


def test_negative_duration_rejected(tmp_path):
    raw = [_span("review", None, "2026-08-04T10:00:00+00:00", "2026-08-04T10:10:00+00:00", -5)]
    valid, rejected = itn.normalize_iterate_timings(raw)
    assert not valid and len(rejected) == 1


def test_duration_grossly_inconsistent_with_its_own_interval_is_rejected(tmp_path):
    """External code review: duration_ms (time.monotonic()) and start/end_utc
    (datetime.now()) are two independent clock readings for a producer span —
    a corrupted record claiming a 1-minute interval with a multi-hour
    duration must be rejected, not silently trusted into impossible
    exclusive-time percentages."""
    raw = [_span("review", None, "2026-08-04T10:00:00+00:00", "2026-08-04T10:01:00+00:00",
                60 * 60 * 1000)]  # 1-hour duration claimed over a 1-minute interval
    valid, rejected = itn.normalize_iterate_timings(raw)
    assert not valid
    assert len(rejected) == 1
    assert "inconsistent" in rejected[0]["reason"]


def test_completed_outcome_with_no_end_utc_is_rejected(tmp_path):
    """External code review: outcome='completed' is a claim about having a
    real bounded interval — a record claiming completed with no end_utc is
    contradictory (not merely incomplete), and would otherwise render the
    nonsensical '*completed* (started, not closed)' in the report."""
    raw = [{"event": "span", "name": "review", "parent": None, "attempt": 1,
           "source": "producer", "outcome": "completed",
           "start_utc": "2026-08-04T10:00:00+00:00", "end_utc": None,
           "duration_ms": None, "extra": {}}]
    valid, rejected = itn.normalize_iterate_timings(raw)
    assert not valid
    assert "requires both end_utc and duration_ms" in rejected[0]["reason"]


def test_completed_outcome_with_end_utc_but_no_duration_is_rejected(tmp_path):
    raw = [{"event": "span", "name": "review", "parent": None, "attempt": 1,
           "source": "producer", "outcome": "completed",
           "start_utc": "2026-08-04T10:00:00+00:00",
           "end_utc": "2026-08-04T10:05:00+00:00",
           "duration_ms": None, "extra": {}}]
    valid, rejected = itn.normalize_iterate_timings(raw)
    assert not valid
    assert "requires both end_utc and duration_ms" in rejected[0]["reason"]


def test_duration_within_tolerance_of_its_interval_is_accepted(tmp_path):
    """Legitimate wall/monotonic drift (e.g. an NTP correction mid-span on a
    long-running iterate) must not false-reject a real span."""
    raw = [_span("review", None, "2026-08-04T10:00:00+00:00", "2026-08-04T10:10:00+00:00",
                10 * 60 * 1000 - 2000)]  # 2s under the 10-minute interval — within tolerance
    valid, rejected = itn.normalize_iterate_timings(raw)
    assert not rejected
    assert valid[0]["name"] == "review"


def test_child_outside_parent_bounds_is_impossible_ordering(tmp_path):
    """A child that starts before its claimed parent is a corrupt relationship,
    not legitimate data — reject that entry, keep the rest."""
    raw = [
        _span("review", None, "2026-08-04T10:00:00+00:00", "2026-08-04T10:10:00+00:00", 600000),
        _span("code_review", "review", "2026-08-04T09:59:00+00:00",
             "2026-08-04T10:05:00+00:00", 360000),  # starts BEFORE its parent
    ]
    valid, rejected = itn.normalize_iterate_timings(raw)
    names = {v["name"] for v in valid}
    assert "review" in names and "code_review" not in names
    assert any("impossible ordering" in r["reason"] or "no containing parent" in r["reason"]
              for r in rejected)


def test_nested_spans_are_not_double_counted(tmp_path):
    """Exclusive time: a parent whose children fully cover it has exclusive_ms
    == 0, and children's own durations are each fully counted once."""
    raw = [
        _span("review", None, "2026-08-04T10:00:00+00:00", "2026-08-04T10:10:00+00:00", 600000),
        _span("self_review", "review", "2026-08-04T10:00:00+00:00",
             "2026-08-04T10:03:00+00:00", 180000),
        _span("code_review", "review", "2026-08-04T10:03:00+00:00",
             "2026-08-04T10:10:00+00:00", 420000),
    ]
    valid, rejected = itn.normalize_iterate_timings(raw)
    assert not rejected
    by_name = {v["name"]: v for v in valid}
    assert by_name["review"]["exclusive_ms"] == 0
    assert by_name["self_review"]["exclusive_ms"] == 180000
    assert by_name["code_review"]["exclusive_ms"] == 420000
    # sum of every node's exclusive == the root's inclusive duration
    assert sum(v["exclusive_ms"] for v in valid) == by_name["review"]["duration_ms"]


def test_partial_coverage_leaves_parent_exclusive_time_visible(tmp_path):
    """Children covering only PART of the parent leave the rest as the
    parent's own exclusive time — never silently dropped."""
    raw = [
        _span("verification", None, "2026-08-04T10:00:00+00:00",
             "2026-08-04T10:23:26+00:00", 1406000),
        _span("f0_queue", "verification", "2026-08-04T10:00:02+00:00",
             "2026-08-04T10:18:02+00:00", 1080000, weight=22, capacity=22),
    ]
    valid, _ = itn.normalize_iterate_timings(raw)
    by_name = {v["name"]: v for v in valid}
    assert by_name["verification"]["exclusive_ms"] == 1406000 - 1080000


# --------------------------------------------------------------------------- #
# Synthetic weight-22 F0 blocker case (matches the P1.16 rollout shape:
# canonical F0 active 5.4 min, queued 18.0 min behind a weight-22 sibling)
# --------------------------------------------------------------------------- #

def test_f0_queue_and_active_execution_are_distinguishable_weight22(tmp_path):
    it.record_start(tmp_path, RUN, name="verification", parent=None,
                    ts="2026-08-04T10:00:00+00:00")
    it.record_producer_span(tmp_path, RUN, name="pre_f0_validation", parent="verification",
                            start_utc="2026-08-04T10:00:00+00:00",
                            end_utc="2026-08-04T10:00:02+00:00", duration_ms=2000)
    it.record_producer_span(tmp_path, RUN, name="f0_queue", parent="verification",
                            start_utc="2026-08-04T10:00:02+00:00",
                            end_utc="2026-08-04T10:18:02+00:00", duration_ms=18 * 60 * 1000,
                            extra={"weight": 22, "capacity": 22, "blocker_owner": "sibling-f0"})
    it.record_producer_span(tmp_path, RUN, name="canonical_f0_active", parent="verification",
                            start_utc="2026-08-04T10:18:02+00:00",
                            end_utc="2026-08-04T10:23:26+00:00", duration_ms=int(5.4 * 60 * 1000))
    it.record_end(tmp_path, RUN, name="verification", parent=None, ts="2026-08-04T10:23:26+00:00")

    valid, rejected = itn.normalize_iterate_timings(itn.read_raw_events(tmp_path, RUN))
    assert not rejected
    by_name = {v["name"]: v for v in valid}
    assert by_name["f0_queue"]["duration_ms"] == 18 * 60 * 1000
    assert by_name["canonical_f0_active"]["duration_ms"] == int(5.4 * 60 * 1000)
    assert by_name["f0_queue"]["duration_ms"] != by_name["canonical_f0_active"]["duration_ms"]
    assert by_name["f0_queue"]["extra"]["weight"] == 22
    assert by_name["verification"]["exclusive_ms"] == 0  # fully accounted by children


# --------------------------------------------------------------------------- #
# CI retry attribution — multiple ci_wait attempts distinguishable
# --------------------------------------------------------------------------- #

def test_ci_wait_attempts_are_individually_attributed(tmp_path):
    raw = [
        _span("delivery", None, "2026-08-04T10:00:00+00:00",
             "2026-08-04T11:00:00+00:00", 3600000),
        _span("delivery_wait", "delivery", "2026-08-04T10:00:00+00:00",
             "2026-08-04T11:00:00+00:00", 3600000),
        {**_span("ci_wait", "delivery_wait", "2026-08-04T10:00:00+00:00",
                "2026-08-04T10:20:00+00:00", 1200000), "attempt": 1},
        {**_span("ci_wait", "delivery_wait", "2026-08-04T10:40:00+00:00",
                "2026-08-04T11:00:00+00:00", 1200000), "attempt": 2},
    ]
    valid, rejected = itn.normalize_iterate_timings(raw)
    assert not rejected
    ci_waits = [v for v in valid if v["name"] == "ci_wait"]
    assert len(ci_waits) == 2
    assert {v["attempt"] for v in ci_waits} == {1, 2}
    # the 20-minute gap between attempt 1 and attempt 2 is post_ci_remediation
    # territory — this run recorded none, and that must show up as unattributed,
    # not vanish.
    delivery_wait = next(v for v in valid if v["name"] == "delivery_wait")
    assert delivery_wait["exclusive_ms"] == 3600000 - 1200000 - 1200000


# --------------------------------------------------------------------------- #
# Overlapping siblings — union, not sum (external plan-review finding)
# --------------------------------------------------------------------------- #

def test_overlapping_siblings_use_interval_union_not_sum(tmp_path):
    """Two children of the same parent that overlap must not double-count the
    overlapped wall-clock — naive duration summation would under-report (or
    zero-clamp) the parent's own exclusive time."""
    raw = [
        _span("review", None, "2026-08-04T10:00:00+00:00", "2026-08-04T10:10:00+00:00", 600000),
        # Two overlapping children: [10:00,10:07] and [10:05,10:10] — union
        # covers the WHOLE parent (600000ms), even though summing their raw
        # durations (420000 + 300000 = 720000) would exceed it.
        _span("self_review", "review", "2026-08-04T10:00:00+00:00",
             "2026-08-04T10:07:00+00:00", 420000),
        _span("remediation", "review", "2026-08-04T10:05:00+00:00",
             "2026-08-04T10:10:00+00:00", 300000),
    ]
    valid, rejected = itn.normalize_iterate_timings(raw)
    assert not rejected
    by_name = {v["name"]: v for v in valid}
    assert by_name["review"]["exclusive_ms"] == 0  # fully covered by the union
    assert by_name["self_review"]["exclusive_ms"] == 420000
    assert by_name["remediation"]["exclusive_ms"] == 300000


def test_partially_overlapping_siblings_leave_correct_gap(tmp_path):
    raw = [
        _span("review", None, "2026-08-04T10:00:00+00:00", "2026-08-04T10:20:00+00:00", 1200000),
        _span("self_review", "review", "2026-08-04T10:00:00+00:00",
             "2026-08-04T10:07:00+00:00", 420000),
        _span("remediation", "review", "2026-08-04T10:05:00+00:00",
             "2026-08-04T10:10:00+00:00", 300000),
    ]
    valid, _ = itn.normalize_iterate_timings(raw)
    review = next(v for v in valid if v["name"] == "review")
    # union of [10:00,10:07] and [10:05,10:10] = 10 minutes covered;
    # 20-minute parent minus that = 10 minutes (600000ms) of real gap.
    assert review["exclusive_ms"] == 1200000 - 600000


# --------------------------------------------------------------------------- #
# Ambiguous parent resolution — most-recently-opened wins, cascade rejection
# --------------------------------------------------------------------------- #

def test_most_recently_opened_open_ended_parent_wins_ties(tmp_path):
    """Two top-level groups left open simultaneously (an agent forgot to
    close the earlier one) must not always resolve to whichever sorts first
    alphabetically — the one opened most recently relative to the child is
    the more plausible enclosing scope."""
    def _open(name, start):
        # A still-open span cannot claim outcome="completed" (validate_entry
        # now rejects that contradiction) — "incomplete" is the honest state
        # of a group an agent forgot to close.
        s = _span(name, None, start, None, None)
        s["outcome"] = "incomplete"
        return s

    raw = [
        # "planning" opened first and was never closed (agent forgot).
        _open("planning", "2026-08-04T09:00:00+00:00"),
        # "review" opened later, also still open.
        _open("review", "2026-08-04T10:00:00+00:00"),
        # external_review starts after BOTH are open; "review" opened more
        # recently and is the semantically correct parent for a code-mode call.
        _span("external_review", "review", "2026-08-04T10:05:00+00:00",
             "2026-08-04T10:06:00+00:00", 60000),
    ]
    valid, rejected = itn.normalize_iterate_timings(raw)
    assert not rejected
    ext = next(v for v in valid if v["name"] == "external_review")
    assert ext["parent"] == "review"


def test_a_child_attached_to_a_rejected_parent_cascades_the_rejection(tmp_path):
    """A child's candidate parent is drawn from ALL entries, not just
    already-validated ones — so a child can attach to an instance that is
    itself rejected (no valid parent of ITS own). A REAL 'delivery' entry
    exists here but does not temporally contain 'delivery_wait' (ends before
    it starts) — impossible ordering, not an absent name, so it is rejected
    rather than synthesized around (see test_iterate_timings_synthesis.py
    for the absent-name case). 'ci_wait' cascades too."""
    raw = [
        _span("delivery", None, "2026-08-04T09:00:00+00:00",
             "2026-08-04T09:30:00+00:00", 1800000),
        _span("delivery_wait", "delivery", "2026-08-04T10:00:00+00:00",
             "2026-08-04T11:00:00+00:00", 3600000),
        _span("ci_wait", "delivery_wait", "2026-08-04T10:10:00+00:00",
             "2026-08-04T10:20:00+00:00", 600000),
    ]
    valid, rejected = itn.normalize_iterate_timings(raw)
    assert {v["name"] for v in valid} == {"delivery"}
    assert {r["raw"]["name"] for r in rejected} == {"delivery_wait", "ci_wait"}
    ci_wait_rejection = next(r for r in rejected if r["raw"]["name"] == "ci_wait")
    assert "itself rejected" in ci_wait_rejection["reason"]
