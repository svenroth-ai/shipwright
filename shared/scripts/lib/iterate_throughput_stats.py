#!/usr/bin/env python3
"""Pure computation over ``work_completed.iterate_timings`` — no I/O.

Sibling of ``iterate_throughput_render.py`` (markdown) and the orchestrating
``tools/iterate_throughput_report.py`` (reads events, writes the file). Split
three ways so each stays testable and under the file-size guideline.
"""

from __future__ import annotations

import statistics
from datetime import datetime, timezone

from lib.iterate_timings import FOLD_TIME_CAPTURABLE_SPANS, TOP_LEVEL_SPANS
from lib.iterate_timings_normalize import union_duration_ms

ROLLING_WINDOW = 10


def _parse_dt(value):
    if not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def iterate_work_completed_events(events: list[dict]) -> list[dict]:
    """Filter + chronologically sort this project's iterate work_completed events."""
    rows = [e for e in events if e.get("type") == "work_completed" and e.get("source") == "iterate"]
    rows.sort(key=lambda e: _parse_dt(e.get("ts")) or datetime.min.replace(tzinfo=timezone.utc))
    return rows


_SOURCE_RANK = {"producer": 0, "agent": 1, "derived": 2}


def _select_top_level(spans: list[dict]) -> dict[str, dict]:
    """Pick ONE representative per top-level name when duplicates exist.

    Two top-level instances of the same name are valid (e.g. a redundant
    agent ``start delivery`` mark alongside ``deliver_pr.py``'s own
    self-recorded producer span — see ``deliver_pr_timing.py``). A bare
    dict comprehension keyed by name silently keeps whichever happens to
    sort last, which can pick the shorter/less-accurate instance and skew
    ``total_ms``/``unattributed_ms`` for the whole run (code review). Prefer
    producer over agent over derived, then bounded over open-ended, then the
    longest duration — the same "most-accurate-wins" intuition as
    ``_attach_parents``'s tiebreak, applied here for reporting rather than
    child-attachment. ``derived`` ranks LAST, not merely below producer: a
    derived entry is a reconstruction with no real recorded boundary at all,
    so it must never silently outrank an actual agent mark, even a bare one
    — "an agent-emitted parent, when present, must always win over the
    derived one" is a hard requirement (iterate-timings.md), and this rank
    is what enforces it wherever both could ever appear side by side (found
    in doubt review — the original placeholder ordering had this backwards,
    untested until synthesis could actually produce a ``derived`` entry).
    """
    candidates: dict[str, list[dict]] = {}
    for s in spans:
        if s.get("parent") is None and s.get("name") in TOP_LEVEL_SPANS:
            candidates.setdefault(s["name"], []).append(s)
    return {
        name: min(
            entries,
            key=lambda e: (
                _SOURCE_RANK.get(e.get("source"), 3),
                0 if e.get("end_utc") else 1,
                -(e.get("duration_ms") or 0),
            ),
        )
        for name, entries in candidates.items()
    }


def run_stat(event: dict) -> dict:
    """Compute one run's throughput stats. Never raises — degrades to ``has_timings: False``.

    ``spans`` here are ALREADY validated (they came from
    :func:`lib.iterate_timings_normalize.fold_into_event`, which only persists
    entries that survived :func:`normalize_iterate_timings`) — this function
    does not re-validate, only aggregates.
    """
    run_id = event.get("adr_id") or "unknown"
    spans = event.get("iterate_timings")
    base = {"run_id": run_id, "ts": event.get("ts"), "has_timings": False,
           "pre_instrumentation": spans is None}
    if not isinstance(spans, list) or not spans:
        return base

    top_level = _select_top_level(spans)
    starts = [_parse_dt(s.get("start_utc")) for s in top_level.values()]
    starts = [d for d in starts if d is not None]
    ends = [_parse_dt(s.get("end_utc")) for s in top_level.values() if s.get("end_utc")]
    total_ms = None
    if starts and ends:
        total_ms = max(0, int((max(ends) - min(starts)).total_seconds() * 1000))

    phases = {}
    for name in TOP_LEVEL_SPANS:
        entry = top_level.get(name)
        if entry is None:
            phases[name] = {"present": False}
            continue
        excl = entry.get("exclusive_ms")
        pct = round(100.0 * excl / total_ms, 1) if (total_ms and excl is not None) else None
        phases[name] = {
            "present": True, "outcome": entry.get("outcome"), "source": entry.get("source"),
            "duration_ms": entry.get("duration_ms"), "exclusive_ms": excl, "pct": pct,
        }

    # Union, not sum: exclusive_ms is disjoint WITHIN one parent's own
    # children, but separate top-level branches (or agent marks left open
    # across a boundary) can still overlap each other in wall-clock terms —
    # summing exclusive_ms across ALL spans would then double-count that
    # overlap and under-report (or even negative-clamp) unattributed time
    # (external plan review, round 2). The union of every span's own
    # [start, end] interval is exactly "time covered by at least one span",
    # regardless of how the hierarchy resolved — mathematically safe even
    # when two branches overlap.
    #
    # Clipped to [min(starts), max(ends)] (the SAME envelope total_ms uses):
    # `total_ms` is built only from `_select_top_level`'s chosen top-level
    # representatives, but `spans` here still includes every span in the
    # event, including a DISCARDED duplicate top-level instance and any
    # child `_attach_parents` happened to contain under it (a separate,
    # independent selection). Without clipping, such a span can fall outside
    # the envelope and push covered_ms above total_ms, silently clamping
    # unattributed_ms to 0 even when a real gap exists (external code review).
    envelope_start = min(starts) if starts else None
    envelope_end = max(ends) if ends else None
    covered_intervals = []
    for s in spans:
        s_start = _parse_dt(s.get("start_utc"))
        s_end = _parse_dt(s.get("end_utc"))
        if s_start is None or s_end is None or envelope_start is None or envelope_end is None:
            continue
        clipped_start = max(s_start, envelope_start)
        clipped_end = min(s_end, envelope_end)
        if clipped_end > clipped_start:
            covered_intervals.append((clipped_start, clipped_end))
    covered_ms = union_duration_ms(covered_intervals)
    unattributed_ms = max(0, total_ms - covered_ms) if total_ms is not None else None
    unattributed_pct = (round(100.0 * unattributed_ms / total_ms, 1)
                        if (total_ms and unattributed_ms is not None) else None)

    nested_by_name: dict[str, list[dict]] = {}
    for s in spans:
        if s.get("parent") is not None:
            nested_by_name.setdefault(s["name"], []).append(s)

    restarts = sum(1 for s in spans if isinstance(s.get("extra"), dict) and s["extra"].get("restart_reason"))
    # Coverage/degraded is measured against FOLD_TIME_CAPTURABLE_SPANS, not
    # all 7 — finalization/delivery are structurally never closed (or, for
    # delivery, never even present) at F5b fold time in every run, so
    # counting them would pin "degraded" to True forever (doubt review).
    # They still render in `phases` below when present; they just don't
    # count against a "clean" run's coverage.
    #
    # "present" alone is not "captured": a top-level span with only a start
    # mark (no end_utc) or an outcome of incomplete/unavailable is exactly
    # the partial-run case this report exists to surface, not to hide behind
    # a clean-looking N/N (external code review) — a run with five bare
    # `start` marks and no matching ends must not read as fully covered. A
    # DERIVED span (materialized from producer children when the agent never
    # marked the boundary — see iterate_timings_synthesis.py) carries real
    # duration data and is shown in the table, but it is a reconstruction,
    # not a measured boundary, so it does not count toward "coverage" either
    # — that metric means "the agent/producer actually marked this," and a
    # fully-derived run should still read as degraded (the agent boundary is
    # genuinely still missing), just no longer as ZERO data.
    coverage_n = sum(
        1 for name in FOLD_TIME_CAPTURABLE_SPANS
        if phases[name]["present"] and phases[name].get("duration_ms") is not None
        and phases[name].get("outcome") not in ("incomplete", "unavailable")
        and phases[name].get("source") != "derived"
    )
    derived_n = sum(
        1 for name in FOLD_TIME_CAPTURABLE_SPANS if phases[name].get("source") == "derived"
    )

    return {
        **base, "has_timings": True, "pre_instrumentation": False,
        "total_ms": total_ms, "coverage_top_level": coverage_n,
        "coverage_top_level_total": len(FOLD_TIME_CAPTURABLE_SPANS), "span_count": len(spans),
        "degraded": coverage_n < len(FOLD_TIME_CAPTURABLE_SPANS),
        "derived_top_level": derived_n,
        "phases": phases, "nested": nested_by_name,
        "unattributed_ms": unattributed_ms, "unattributed_pct": unattributed_pct,
        "restarts": restarts,
    }


def rolling_percentiles(run_stats: list[dict], *, field_path: tuple[str, ...],
                        window: int = ROLLING_WINDOW) -> dict:
    """Median/P90 of a numeric field across the last ``window`` runs that have it.

    ``field_path`` walks nested dicts, e.g. ``("phases", "review", "exclusive_ms")``.
    Returns ``{"median": x, "p90": y, "n": n}`` or ``{"n": 0}`` if no samples exist.
    """
    values: list[float] = []
    for stat in run_stats[-window:]:
        node = stat
        for key in field_path:
            if not isinstance(node, dict):
                node = None
                break
            node = node.get(key)
        if isinstance(node, (int, float)) and not isinstance(node, bool):
            values.append(float(node))
    if not values:
        return {"n": 0}
    values.sort()
    result = {"n": len(values), "median": statistics.median(values)}
    if len(values) >= 2:
        result["p90"] = statistics.quantiles(values, n=10)[8] if len(values) >= 10 else max(values)
    return result
