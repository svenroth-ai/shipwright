#!/usr/bin/env python3
"""Pure computation over ``work_completed.iterate_timings`` — no I/O.

Sibling of ``iterate_throughput_render.py`` (markdown) and the orchestrating
``tools/iterate_throughput_report.py`` (reads events, writes the file). Split
three ways so each stays testable and under the file-size guideline.
"""

from __future__ import annotations

import statistics
from datetime import datetime, timezone

from lib.iterate_timings import FOLD_TIME_CAPTURABLE_SPANS, TOP_LEVEL_SPANS, agent_span_max_ms
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


def _is_implausible_agent_span(span: dict) -> bool:
    """Whether a durable agent span exceeds its name-specific credible duration."""
    duration_ms = span.get("duration_ms")
    return (
        span.get("source") == "agent"
        and span.get("outcome") in ("completed", "cancelled")
        and isinstance(duration_ms, (int, float))
        and not isinstance(duration_ms, bool)
        and duration_ms > agent_span_max_ms(span.get("name", ""))
    )


def _is_usable_work_span(span: dict) -> bool:
    """True for a bounded outcome that may represent credible work."""
    return (
        span.get("outcome") in ("completed", "cancelled")
        and not _is_implausible_agent_span(span)
    )


def _selection_rank(span: dict) -> int:
    """Prefer a successful credible attempt over a cancelled one."""
    if not _is_usable_work_span(span):
        return 2
    return 0 if span.get("outcome") == "completed" else 1


def _open_finalization_duration_ms(span: dict, completed_at):
    """Return the inferable F5b-bounded finalization duration, if any."""
    if (
        span.get("source") != "agent"
        or span.get("name") != "finalization"
        or span.get("parent") is not None
        or span.get("outcome") != "incomplete"
        or span.get("end_utc")
    ):
        return None
    started_at = _parse_dt(span.get("start_utc"))
    if started_at is None or completed_at is None or completed_at < started_at:
        return None
    return int((completed_at - started_at).total_seconds() * 1000)


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
                _selection_rank(e),
                0 if e.get("end_utc") else 1,
                -(e.get("duration_ms") or 0),
            ),
        )
        for name, entries in candidates.items()
    }


def _scope_started_at(event: dict):
    """Return the durable scope boundary, or ``None`` when it was never marked."""
    phase_timings = event.get("phase_timings")
    if not isinstance(phase_timings, list):
        return None
    for phase in phase_timings:
        if isinstance(phase, dict) and phase.get("phase") == "scope":
            return _parse_dt(phase.get("started"))
    return None


def run_stat(event: dict) -> dict:
    """Compute one run's throughput stats. Never raises — degrades to ``has_timings: False``.

    ``spans`` here are ALREADY validated (they came from
    :func:`lib.iterate_timings_normalize.fold_into_event`, which only persists
    entries that survived :func:`normalize_iterate_timings`) — this function
    does not re-validate, only aggregates.
    """
    run_id = event.get("adr_id") or "unknown"
    scope_start = _scope_started_at(event)
    spans = event.get("iterate_timings")
    if spans is None and scope_start is not None:
        # A current scope mark with no folded spans is a measured zero-
        # emission run, not a pre-instrumentation historical record.
        spans = []
    base = {"run_id": run_id, "ts": event.get("ts"), "has_timings": False,
           "pre_instrumentation": spans is None}
    if not isinstance(spans, list):
        return base

    top_level = _select_top_level(spans)
    starts = [_parse_dt(s.get("start_utc")) for s in top_level.values()]
    starts = [d for d in starts if d is not None]
    ends = [_parse_dt(s.get("end_utc")) for s in top_level.values() if s.get("end_utc")]
    total_ms = None
    if starts and ends:
        total_ms = max(0, int((max(ends) - min(starts)).total_seconds() * 1000))

    completed_at = _parse_dt(event.get("ts"))
    phases = {}
    for name in TOP_LEVEL_SPANS:
        entry = top_level.get(name)
        if entry is None:
            phases[name] = {"present": False}
            continue
        inferred_finalization_ms = _open_finalization_duration_ms(entry, completed_at)
        implausible = (
            _is_implausible_agent_span(entry)
            or (
                inferred_finalization_ms is not None
                and inferred_finalization_ms > agent_span_max_ms("finalization")
            )
        )
        unavailable = entry.get("outcome") == "unavailable" or implausible
        recorded_duration_ms = entry.get("duration_ms") if unavailable else None
        if unavailable and recorded_duration_ms is None:
            recorded_duration_ms = inferred_finalization_ms
        excl = None if unavailable else entry.get("exclusive_ms")
        duration_ms = None if unavailable else entry.get("duration_ms")
        pct = round(100.0 * excl / total_ms, 1) if (total_ms and excl is not None) else None
        unavailable_reason = (entry.get("extra") or {}).get("unavailable_reason")
        if implausible:
            unavailable_reason = "implausible_duration"
        phases[name] = {
            "present": True, "outcome": "unavailable" if unavailable else entry.get("outcome"),
            "source": entry.get("source"), "duration_ms": duration_ms,
            "exclusive_ms": excl, "pct": pct,
            "recorded_duration_ms": recorded_duration_ms,
            "unavailable_reason": unavailable_reason,
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
    # The durable scope mark is the run's real start boundary; the
    # work_completed event timestamp is its F5b end. Historic runs that have
    # no scope mark cannot prove wall time, so they report it as unavailable.
    wall_ms = None
    coverage_reason = None
    if scope_start is None:
        coverage_reason = "missing_scope_mark"
    elif completed_at is None or completed_at < scope_start:
        coverage_reason = "invalid_scope_wall"
    else:
        wall_ms = int((completed_at - scope_start).total_seconds() * 1000)

    # Union, not sum: nested and top-level spans can overlap. Only bounded
    # work intervals count; an unavailable agent span remains visible as
    # implausible-duration evidence but cannot inflate coverage.
    envelope_start = scope_start if wall_ms is not None else (min(starts) if starts else None)
    envelope_end = completed_at if wall_ms is not None else (max(ends) if ends else None)
    covered_intervals = []
    for s in spans:
        bounded_work = _is_usable_work_span(s)
        finalization_duration_ms = _open_finalization_duration_ms(s, envelope_end)
        bounded_finalization = (
            wall_ms is not None
            and finalization_duration_ms is not None
            and finalization_duration_ms <= agent_span_max_ms("finalization")
        )
        if not bounded_work and not bounded_finalization:
            continue
        s_start = _parse_dt(s.get("start_utc"))
        s_end = _parse_dt(s.get("end_utc")) if bounded_work else envelope_end
        if s_start is None or s_end is None or envelope_start is None or envelope_end is None:
            continue
        clipped_start = max(s_start, envelope_start)
        clipped_end = min(s_end, envelope_end)
        if clipped_end > clipped_start:
            covered_intervals.append((clipped_start, clipped_end))
    instrumented_ms = union_duration_ms(covered_intervals)
    denominator_ms = wall_ms if wall_ms is not None else total_ms
    unattributed_ms = max(0, denominator_ms - instrumented_ms) if denominator_ms is not None else None
    unattributed_pct = (round(100.0 * unattributed_ms / denominator_ms, 1)
                         if (denominator_ms and unattributed_ms is not None) else None)
    instrumented_ratio = (round(instrumented_ms / wall_ms, 4) if wall_ms else None)

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
    # Discovery and planning are alternative entry paths. A run that recorded
    # exactly one should not be penalized for the other never starting.
    capturable_spans = set(FOLD_TIME_CAPTURABLE_SPANS)
    has_discovery = phases["discovery_diagnosis"]["present"]
    has_planning = phases["planning"]["present"]
    entry_path = None
    if has_discovery != has_planning:
        entry_path = "discovery_diagnosis" if has_discovery else "planning"
        capturable_spans.discard("planning" if has_discovery else "discovery_diagnosis")
    coverage_n = sum(
        1 for name in capturable_spans
        if phases[name]["present"] and phases[name].get("duration_ms") is not None
        and phases[name].get("outcome") not in ("incomplete", "unavailable")
        and phases[name].get("source") != "derived"
    )
    derived_n = sum(
        1 for name in capturable_spans if phases[name].get("source") == "derived"
    )

    return {
        **base, "has_timings": True, "pre_instrumentation": False,
        "total_ms": total_ms, "coverage_top_level": coverage_n,
        "coverage_top_level_total": len(capturable_spans), "span_count": len(spans),
        "entry_path": entry_path,
        "degraded": coverage_n < len(capturable_spans),
        "derived_top_level": derived_n,
        "phases": phases, "nested": nested_by_name,
        "wall_ms": wall_ms, "instrumented_ms": instrumented_ms,
        "instrumented_ratio": instrumented_ratio, "coverage_reason": coverage_reason,
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
