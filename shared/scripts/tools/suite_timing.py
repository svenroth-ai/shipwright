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
from scripts.lib.iterate_timings import (
    record_producer_span_counted as _record_timing_span_counted,
)

#: process-local: which attempt THIS process resolved for (root, run_id).
#: Never persisted - a fresh process always re-resolves from the sidecar.
_attempt_cache: dict[tuple[str, str], int] = {}


def _cache_key(root: Path, run_id: str) -> tuple[str, str]:
    return (str(Path(root).resolve()), run_id)


def _count_prior_attempts(entries: list) -> int:
    """F0-specific counting POLICY (kept out of iterate_timings.py, which
    stays span-shape-agnostic): the max of three per-stage counts, so a
    process killed anywhere between the warmup-lease grant and the
    canonical-active write still yields a distinct next attempt rather than
    colliding with the one it interrupted. A legacy `f0_queue` entry with no
    `stage` key (every real entry recorded before this change) counts as
    "cpu" - conservative, and already paired with its own `canonical_f0_active`
    for every historical run, so it changes no observed count."""
    warmup = cpu = canonical = 0
    for entry in entries:
        if entry.get("event") != "span":
            continue
        name = entry.get("name")
        if name == "f0_queue":
            extra = entry.get("extra")
            # doubt review: a truthy non-dict `extra` (hand-corrupted sidecar
            # line) must not raise here - this runs INSIDE the resolver's
            # lock, and the poisoned line stays in the file, so a crash would
            # break every future attempt-resolution in the run, not just this
            # one call.
            if isinstance(extra, dict) and extra.get("stage") == "warmup":
                warmup += 1
            else:
                cpu += 1
        elif name == "canonical_f0_active":
            canonical += 1
    return max(warmup, cpu, canonical)


def _record_span_resolving_attempt(root: Path, run_id: str, *, name: str, parent: str,
                                   start_utc: str, end_utc: str | None,
                                   duration_ms: int | None, outcome: str = "completed",
                                   extra: dict | None = None) -> int:
    """Whichever of the three producer calls is first (per process) to have
    something of its own to write resolves the attempt atomically - under
    record_producer_span_counted's lock, count-then-append in one critical
    section, so a concurrent second process cannot read before this one has
    durably written. Later calls in the SAME process reuse the cached value
    via an ordinary (uncounted, unlocked-beyond-the-write-itself) append -
    no other process can be "in between" for a span this process already
    holds the resolved number for."""
    key = _cache_key(root, run_id)
    cached = _attempt_cache.get(key)
    if cached is not None:
        _record_timing_span(
            root, run_id, name=name, parent=parent, attempt=cached,
            outcome=outcome, start_utc=start_utc, end_utc=end_utc,
            duration_ms=duration_ms, extra=extra,
        )
        return cached
    _, attempt = _record_timing_span_counted(
        root, run_id, name=name, parent=parent, outcome=outcome,
        start_utc=start_utc, end_utc=end_utc, duration_ms=duration_ms,
        extra=extra, count_prior=_count_prior_attempts,
    )
    _attempt_cache[key] = attempt
    return attempt


def record_f0_queue_span(root: Path, run_id: str | None, *, waited_seconds: float,
                         weight: int, capacity: int, stage: str) -> None:
    """f0_queue is a real producer boundary: LeaseGrant.waited_seconds is already
    computed by host_resource_lease - this only persists what it discards today.
    Best-effort and scoped to canonical iterate run_ids (a bare "iterate-"
    prefix check would also match a malformed id like "iterate-not-canonical";
    RUN_ID_STRICT is the same gate iterate_timing.py's CLI enforces -
    external code review). Ad-hoc F0 invocations outside an iterate have no
    work_completed event to fold into. `stage` ("warmup" or "cpu") is written
    into `extra` so a later invocation's attempt-count can tell the two
    `f0_queue` call sites apart (test-phase-attribution)."""
    if not run_id or not RUN_ID_STRICT.match(run_id) or waited_seconds <= 0:
        return
    now = datetime.now(timezone.utc)
    start = now - timedelta(seconds=waited_seconds)
    try:
        _record_span_resolving_attempt(
            root, run_id, name="f0_queue", parent="verification",
            start_utc=start.isoformat(), end_utc=now.isoformat(),
            duration_ms=max(0, int(waited_seconds * 1000)),
            extra={"weight": weight, "capacity": capacity, "stage": stage},
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
        _record_span_resolving_attempt(
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
        parent_end = active_start + timedelta(seconds=duration_seconds)
        attempt = _record_span_resolving_attempt(
            root, run_id, name="canonical_f0_active", parent="verification",
            start_utc=active_start.isoformat(), end_utc=parent_end.isoformat(),
            duration_ms=max(0, int(duration_seconds * 1000)),
            extra={"weight": weight, "capacity": capacity},
        )
    except Exception as exc:  # noqa: BLE001 - timing must never break F0
        print(f"[iterate_timings] canonical_f0_active recording skipped: {exc}",
             file=sys.stderr)
        return
    try:
        _record_unit_results(root, run_id, result, active_start=active_start,
                            parent_end=parent_end, attempt=attempt)
    except Exception as exc:  # noqa: BLE001 - timing must never break F0
        print(f"[iterate_timings] f0_unit_result recording skipped: {exc}",
             file=sys.stderr)


def _record_unit_results(root: Path, run_id: str, result, *, active_start: datetime,
                         parent_end: datetime, attempt: int) -> None:
    """One f0_unit_result span per UnitResult, on the normal-return path
    only (AC4: `run_suite()` raising means no `result.results` to read at
    all - the runner-fault path stays a named, disclosed gap, not silently
    dropped - see the iterate spec's Known Limitations). Each unit gets its
    OWN nested try/except so one shape mismatch never loses a sibling's span
    - and the parent `canonical_f0_active` span above is already durably
    written by the time this runs, so a failure here can never lose it.
    The `getattr`/iteration below is itself wrapped by the caller (external
    code review): a truthy-but-not-iterable `result.results` must degrade
    the same as any other shape mismatch, never propagate out of a timing
    helper and abort an F0 run whose suite already passed."""
    units = getattr(result, "results", None)
    if not units:
        return
    for unit in units:
        try:
            # Clamp the START into the parent's own interval too, not just the
            # end (external code review): a unit's own started_utc can land
            # after parent_end under clock skew or a hand-built UnitResult,
            # and clamping only `end` in that case inverts the interval
            # (end_utc < start_utc) instead of preventing it.
            started = min(max(datetime.fromisoformat(unit.started_utc), active_start),
                         parent_end)
            end = min(started + timedelta(seconds=max(0.0, unit.seconds)), parent_end)
            extra = {"unit": unit.unit_id, "conclusion": unit.outcome}
            if unit.retry_kind:
                extra["retry_shape"] = unit.retry_kind
            _record_timing_span(
                root, run_id, name="f0_unit_result", parent="canonical_f0_active",
                attempt=attempt, outcome="completed",
                start_utc=started.isoformat(), end_utc=end.isoformat(),
                duration_ms=max(0, int((end - started).total_seconds() * 1000)),
                extra=extra,
            )
        except Exception as exc:  # noqa: BLE001 - one unit's span must never cost another's
            print(f"[iterate_timings] f0_unit_result recording skipped for "
                 f"{getattr(unit, 'unit_id', '?')!r}: {exc}", file=sys.stderr)
