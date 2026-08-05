#!/usr/bin/env python3
"""F0 suite runner - timing instrumentation (measurement only).

Split from ``run_test_suite.py`` per ADR-123's own committed extraction
plan: the two producer-owned timing marks below (``f0_queue`` - host-lease
wait time; ``canonical_f0_active`` - the suite's own execution wall-clock)
are self-contained persistence helpers with a single caller each in
``_run_host_leased_suite``, matching this file's established
``suite_*.py`` composition pattern.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from scripts.lib.iterate_entry import RUN_ID_STRICT
from scripts.lib.iterate_timings import record_producer_span as _record_timing_span


def record_f0_queue_span(root: Path, run_id: str | None, *, waited_seconds: float,
                         weight: int, capacity: int) -> None:
    """f0_queue is a real producer boundary: LeaseGrant.waited_seconds is already
    computed by host_resource_lease - this only persists what it discards today.
    Best-effort and scoped to canonical iterate run_ids (a bare "iterate-"
    prefix check would also match a malformed id like "iterate-not-canonical";
    RUN_ID_STRICT is the same gate iterate_timing.py's CLI enforces -
    external code review). Ad-hoc F0 invocations outside an iterate have no
    work_completed event to fold into."""
    if not run_id or not RUN_ID_STRICT.match(run_id) or waited_seconds <= 0:
        return
    now = datetime.now(timezone.utc)
    start = now - timedelta(seconds=waited_seconds)
    try:
        _record_timing_span(
            root, run_id, name="f0_queue", parent="verification",
            start_utc=start.isoformat(), end_utc=now.isoformat(),
            duration_ms=max(0, int(waited_seconds * 1000)),
            extra={"weight": weight, "capacity": capacity},
        )
    except Exception as exc:  # noqa: BLE001 - timing must never break F0
        print(f"[iterate_timings] f0_queue recording skipped: {exc}", file=sys.stderr)


def record_canonical_f0_active_span_failed(root: Path, run_id: str | None, *,
                                           active_start: datetime, weight: int,
                                           capacity: int) -> None:
    """``run_suite()`` raised before returning a result — still a real
    producer boundary, and exactly the run where attribution matters most.
    Persists "we were running for N seconds when it failed" as `incomplete`,
    matching :func:`iterate_timings.span`'s own incomplete-on-exception
    behavior, instead of silently losing the span for every failed run
    (external code review)."""
    if not run_id or not RUN_ID_STRICT.match(run_id):
        return
    try:
        end = datetime.now(timezone.utc)
        duration_ms = max(0, int((end - active_start).total_seconds() * 1000))
        _record_timing_span(
            root, run_id, name="canonical_f0_active", parent="verification",
            start_utc=active_start.isoformat(), end_utc=end.isoformat(),
            duration_ms=duration_ms, outcome="incomplete",
            extra={"weight": weight, "capacity": capacity},
        )
    except Exception as exc:  # noqa: BLE001 - timing must never break F0
        print(f"[iterate_timings] canonical_f0_active (failed run) recording skipped: {exc}",
             file=sys.stderr)


def record_canonical_f0_active_span(root: Path, run_id: str | None, *,
                                    active_start: datetime, result, weight: int,
                                    capacity: int) -> None:
    """canonical_f0_active is run_suite()'s own wall-clock - the active execution
    time distinguishable from the f0_queue wait that may precede it.

    ``result`` is taken as the raw ``run_suite()`` return value (not typed as
    ``SuiteResult`` - that would import back into ``run_test_suite.py`` and
    cycle) so that reading its ``.seconds`` attribute stays INSIDE the
    best-effort guard below, exactly like every other field this function
    touches. A caller that got the shape wrong (a test double, a future
    refactor) must degrade to a skipped span, never a broken F0 run.
    """
    if not run_id or not RUN_ID_STRICT.match(run_id):
        return
    try:
        duration_seconds = result.seconds
        _record_timing_span(
            root, run_id, name="canonical_f0_active", parent="verification",
            start_utc=active_start.isoformat(),
            end_utc=(active_start + timedelta(seconds=duration_seconds)).isoformat(),
            duration_ms=max(0, int(duration_seconds * 1000)),
            extra={"weight": weight, "capacity": capacity},
        )
    except Exception as exc:  # noqa: BLE001 - timing must never break F0
        print(f"[iterate_timings] canonical_f0_active recording skipped: {exc}",
             file=sys.stderr)
