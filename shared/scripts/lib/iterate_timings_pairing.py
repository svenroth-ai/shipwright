#!/usr/bin/env python3
"""Iterate-timing spans — raw-event pairing and per-entry validation.

Split out of ``iterate_timings_normalize.py`` at ~300 lines (file-size
guideline); this module is the private preprocessing step that module's
``normalize_iterate_timings`` calls before hierarchy resolution. Not part of
the public API other files import — see ``iterate_timings_normalize.py`` and
``iterate_timings.py`` for the design contract.
"""

from __future__ import annotations

from datetime import datetime, timezone

from lib.iterate_timings import (
    IterateTimingError,
    agent_span_max_ms,
    OUTCOMES,
    SOURCES,
    validate_extra,
    validate_name_parent,
)


def parse_dt(value) -> datetime | None:
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value)
        except ValueError:
            return None
    else:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def pair_agent_events(raw_events: list[dict]) -> tuple[list[dict], list[dict]]:
    """Pair ``start``/``end`` agent events by ``(name, parent)`` in arrival order.

    First-unmatched-start pairs with the next end for the same key — forgiving
    of an agent that does not increment ``attempt`` correctly. Returns
    ``(paired, rejected)``; a trailing unmatched start is INCOMPLETE (kept,
    not rejected — its absence must be visible, never silently dropped); a
    leading unmatched end is rejected (orphaned).
    """
    by_key: dict[tuple, list[dict]] = {}
    for raw in raw_events:
        if raw.get("event") not in ("start", "end"):
            continue
        key = (raw.get("name"), raw.get("parent"))
        by_key.setdefault(key, []).append(raw)

    paired: list[dict] = []
    rejected: list[dict] = []
    for (name, parent), events in by_key.items():
        # `events` is already in file/append order (raw_events is, and this
        # list is built by a single top-to-bottom pass over it) — pairing
        # trusts THAT order, not each mark's own embedded timestamp. A
        # cross-process wall-clock regression (NTP correction, suspend/
        # resume) can make an "end" mark's ts sort earlier than its "start"
        # even though it was genuinely written second; re-sorting by ts here
        # would silently swap them into looking orphaned instead of paired
        # (doubt review) — real acquisition order (serialized by FileLock)
        # is the trustworthy signal, not the timestamps this function exists
        # to validate.
        pending_start = None
        for ev in events:
            if ev.get("event") == "start":
                if pending_start is not None:
                    # Two starts with no end between them — the earlier one is
                    # incomplete (superseded), the newer one is now pending.
                    paired.append({
                        "name": name, "parent": parent,
                        "attempt": pending_start.get("attempt", 1),
                        "source": "agent", "outcome": "incomplete",
                        "start_utc": pending_start.get("ts"), "end_utc": None,
                        "duration_ms": None, "extra": {},
                    })
                pending_start = ev
            else:  # end
                if pending_start is None:
                    rejected.append({"reason": "orphaned end (no matching start)", "raw": ev})
                    continue
                start_dt = parse_dt(pending_start.get("ts"))
                end_dt = parse_dt(ev.get("ts"))
                duration_ms = None
                outcome = ev.get("outcome", "completed")
                end_ts = ev.get("ts")
                end_extra = ev.get("extra") or {}
                if start_dt is not None and end_dt is not None:
                    if end_dt < start_dt:
                        # Cross-process wall-clock marks have no shared monotonic
                        # source (unlike producer span()); a clock step-back
                        # between the two CLI invocations (NTP correction,
                        # suspend/resume) must never silently clamp to a
                        # fabricated 0ms "completed" span (doubt review) — drop
                        # the untrustworthy end_utc and mark it honestly instead.
                        end_ts = None
                        outcome = "unavailable"
                    else:
                        duration_ms = int((end_dt - start_dt).total_seconds() * 1000)
                        if outcome in ("completed", "cancelled") and duration_ms > agent_span_max_ms(name):
                            # This implausibly long agent interval proves a
                            # missed boundary, not its cause. Preserve its raw
                            # duration as evidence while excluding it from work.
                            outcome = "unavailable"
                            end_extra = dict(end_extra)
                            end_extra["unavailable_reason"] = "implausible_duration"
                paired.append({
                    "name": name, "parent": parent,
                    "attempt": pending_start.get("attempt", 1),
                    "source": "agent", "outcome": outcome,
                    "start_utc": pending_start.get("ts"), "end_utc": end_ts,
                    "duration_ms": duration_ms, "extra": end_extra,
                })
                pending_start = None
        if pending_start is not None:
            paired.append({
                "name": name, "parent": parent,
                "attempt": pending_start.get("attempt", 1),
                "source": "agent", "outcome": "incomplete",
                "start_utc": pending_start.get("ts"), "end_utc": None,
                "duration_ms": None, "extra": {},
            })
    return paired, rejected


def validate_entry(entry: dict) -> dict:
    """Structural validation of one candidate span. Raises IterateTimingError."""
    name = entry.get("name")
    parent = entry.get("parent")
    validate_name_parent(name, parent)
    source = entry.get("source", "agent")
    if source not in SOURCES:
        raise IterateTimingError(f"unknown source {source!r}")
    outcome = entry.get("outcome", "completed")
    if outcome not in OUTCOMES:
        raise IterateTimingError(f"unknown outcome {outcome!r}")
    duration_ms = entry.get("duration_ms")
    if duration_ms is not None:
        if isinstance(duration_ms, bool) or not isinstance(duration_ms, int) or duration_ms < 0:
            raise IterateTimingError(f"duration_ms must be a non-negative int or null, got {duration_ms!r}")
    start_utc = entry.get("start_utc")
    if not isinstance(start_utc, str) or parse_dt(start_utc) is None:
        raise IterateTimingError("start_utc must be a parseable ISO-8601 string")
    end_utc = entry.get("end_utc")
    if end_utc is not None:
        if not isinstance(end_utc, str) or parse_dt(end_utc) is None:
            raise IterateTimingError("end_utc must be a parseable ISO-8601 string or null")
        end_dt, start_dt = parse_dt(end_utc), parse_dt(start_utc)
        if end_dt < start_dt:
            raise IterateTimingError("end_utc precedes start_utc")
        if duration_ms is not None:
            # A producer span's duration_ms (time.monotonic()) and its
            # start/end_utc (datetime.now()) are two INDEPENDENT clock
            # readings, so a corrupted or malicious record could claim a
            # short interval with a wildly larger duration (or vice versa) -
            # exclusive-time and rolling-percentile math would then silently
            # produce impossible percentages instead of rejecting the entry
            # (external code review). Tolerance is generous (2%, 5s floor) to
            # absorb legitimate wall/monotonic drift on long spans - this
            # codebase's own runs have spanned 34+ hours - while still
            # catching a gross mismatch (the reviewer's example: a 1-minute
            # interval claiming a multi-hour duration is ~60x off).
            interval_ms = int((end_dt - start_dt).total_seconds() * 1000)
            tolerance_ms = max(5000, int(0.02 * max(interval_ms, duration_ms)))
            if abs(duration_ms - interval_ms) > tolerance_ms:
                raise IterateTimingError(
                    f"duration_ms ({duration_ms}) inconsistent with the start/end "
                    f"interval ({interval_ms}ms); tolerance {tolerance_ms}ms")
    if outcome == "completed" and (end_utc is None or duration_ms is None):
        # "completed" is a claim about having a real bounded interval - a
        # record claiming completed with no end/duration is contradictory,
        # not merely incomplete data. Left unvalidated, run_stat's coverage
        # check (which keys off duration_ms, not outcome) would correctly
        # decline to count it, but the RENDER layer's outcome-based branch
        # would then print the nonsensical "*completed* (started, not
        # closed)" (external code review) - reject at the write boundary
        # instead of producing a self-contradicting durable record.
        raise IterateTimingError(
            "outcome 'completed' requires both end_utc and duration_ms")
    attempt = entry.get("attempt", 1)
    if isinstance(attempt, bool) or not isinstance(attempt, int) or attempt < 1:
        raise IterateTimingError(f"attempt must be a positive int, got {attempt!r}")
    extra = validate_extra(entry.get("extra"))
    return {
        "name": name, "parent": parent, "source": source, "outcome": outcome,
        "start_utc": start_utc, "end_utc": end_utc, "duration_ms": duration_ms,
        "attempt": attempt, "extra": extra,
    }
