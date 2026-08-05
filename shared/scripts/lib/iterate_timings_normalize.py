#!/usr/bin/env python3
"""Iterate-timing spans — hierarchy resolution, normalization, and the F5b fold.

Sibling of ``iterate_timings.py`` (catalog + writers) and
``iterate_timings_pairing.py`` (raw-event pairing + per-entry validation,
split out at ~300 lines). See ``iterate_timings.py``'s docstring for the
design contract.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone

from lib.iterate_timings import IterateTimingError, SPAN_PARENTS, sidecar_path
from lib.iterate_timings_pairing import pair_agent_events, parse_dt, validate_entry

_MAX_TIMEDELTA = timedelta.max


def read_raw_events(project_root, run_id: str) -> list[dict]:
    """Tolerant JSONL reader. Missing sidecar -> ``[]``. Bad lines are skipped."""
    path = sidecar_path(project_root, run_id)
    if not path.exists():
        return []
    out: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except (ValueError, TypeError):
            continue
        if isinstance(obj, dict):
            out.append(obj)
    return out


def _attach_parents(entries: list[dict]) -> tuple[list[dict], list[dict]]:
    """Assign each nested entry to the temporally-containing parent instance.

    A top-level entry (``parent is None``) always survives. A nested entry
    whose interval is not contained by any surviving candidate-parent
    instance is rejected — this is the "impossible ordering" guard: a child
    cannot start before, or end after, the instance it claims to belong to.
    An incomplete child (no ``end_utc``) only needs ``start >= parent.start``
    (and ``start <= parent.end`` when the parent has already closed).
    """
    by_name: dict[str, list[dict]] = {}
    for e in entries:
        by_name.setdefault(e["name"], []).append(e)

    kept: list[dict] = []
    rejected: list[dict] = []
    for e in entries:
        if e["parent"] is None:
            e["_parent_key"] = None
            kept.append(e)
            continue
        candidates: list[dict] = []
        for pname in sorted(SPAN_PARENTS[e["name"]], key=lambda p: p or ""):
            candidates.extend(by_name.get(pname, []))
        child_start = parse_dt(e["start_utc"])
        child_end = parse_dt(e["end_utc"]) if e["end_utc"] else None
        # Tightest-fitting containing instance wins (deterministic — matches
        # scoping intuition): when two candidate parents both fully contain
        # the child (e.g. a top-level "delivery" and its own nested
        # "delivery_wait" spanning the identical interval), the more specific
        # one is correct, not whichever happened to be inserted first. Sort
        # key: bounded before open-ended, smallest interval first, a
        # candidate that is ITSELF nested (has its own parent) before a
        # top-level one, then the MOST RECENTLY OPENED candidate — the
        # innermost enclosing scope, same intuition as call-stack resolution.
        # That last tiebreak matters when two top-level groups are both left
        # open (an agent forgot to close the earlier one): the one that
        # opened right before this span is far more likely correct than
        # whichever sorts first alphabetically.
        contained = []
        for cand in candidates:
            if cand is e:
                continue
            p_start = parse_dt(cand["start_utc"])
            p_end = parse_dt(cand["end_utc"]) if cand["end_utc"] else None
            if p_start is None or child_start < p_start:
                continue
            if p_end is not None and child_start > p_end:
                continue
            if child_end is not None and p_end is not None and child_end > p_end:
                continue
            span_len = (p_end - p_start) if p_end is not None else None
            contained.append((
                0 if span_len is not None else 1,
                span_len if span_len is not None else _MAX_TIMEDELTA,
                0 if cand.get("parent") is not None else 1,
                child_start - p_start,
                cand,
            ))
        chosen = min(contained, key=lambda t: t[:4])[4] if contained else None
        if chosen is None:
            rejected.append({"reason": f"no containing parent instance for {e['name']!r}", "raw": e})
            continue
        e["_parent_key"] = id(chosen)
        kept.append(e)
    return _cascade_reject_orphans(kept, rejected)


def _cascade_reject_orphans(kept: list[dict], rejected: list[dict]) -> tuple[list[dict], list[dict]]:
    """A child's chosen parent instance is picked independently of whether
    THAT instance itself survives (candidates are drawn from ALL entries,
    not just already-validated ones) — so a child can attach to an instance
    that gets rejected on its own merits, leaving a durable span whose
    claimed parent doesn't exist in the output at all (external code
    review). Iterate to a fixed point: rejecting one orphan can orphan
    another (grandchild) in turn.
    """
    changed = True
    while changed:
        changed = False
        kept_ids = {id(e) for e in kept}
        still_kept: list[dict] = []
        for e in kept:
            key = e.get("_parent_key")
            if key is not None and key not in kept_ids:
                rejected.append({
                    "reason": f"parent instance for {e['name']!r} was itself rejected", "raw": e,
                })
                changed = True
                continue
            still_kept.append(e)
        kept = still_kept
    return kept, rejected


def union_duration_ms(intervals: list[tuple[datetime, datetime]]) -> int:
    """Total wall-clock covered by ``intervals`` — overlaps counted once."""
    bounded = sorted((s, e) for s, e in intervals if s is not None and e is not None and e >= s)
    if not bounded:
        return 0
    total = 0
    cur_start, cur_end = bounded[0]
    for start, end in bounded[1:]:
        if start > cur_end:
            total += int((cur_end - cur_start).total_seconds() * 1000)
            cur_start, cur_end = start, end
        elif end > cur_end:
            cur_end = end
    total += int((cur_end - cur_start).total_seconds() * 1000)
    return total


def normalize_iterate_timings(raw_events: list[dict]) -> tuple[list[dict], list[dict]]:
    """Validate + compute the final span list. Returns ``(valid_spans, rejected)``.

    Per-entry resilience: one malformed span is dropped (with a reason), it
    never voids the rest of the run's data. ``valid_spans`` entries carry
    ``duration_ms`` (inclusive) and ``exclusive_ms`` (inclusive minus the
    UNION of contained children's intervals — clamped at 0, never negative,
    never double counted even when children overlap). Chronological output.
    """
    producer_events = [e for e in raw_events if e.get("event") == "span"]
    paired_agent, agent_rejects = pair_agent_events(raw_events)

    candidates: list[dict] = []
    rejected: list[dict] = list(agent_rejects)
    for raw in producer_events + paired_agent:
        try:
            candidates.append(validate_entry(raw))
        except IterateTimingError as exc:
            rejected.append({"reason": str(exc), "raw": raw})

    kept, parent_rejects = _attach_parents(candidates)
    rejected.extend(parent_rejects)

    children_of: dict[int, list[dict]] = {}
    for e in kept:
        key = e.get("_parent_key")
        if key is not None:
            children_of.setdefault(key, []).append(e)

    out: list[dict] = []
    for e in kept:
        exclusive = e["duration_ms"]
        if exclusive is not None:
            # Union, not sum: two children of the same parent CAN legitimately
            # overlap (e.g. a parallel review pass), and summing their raw
            # durations would double-count the overlap, silently under- or
            # (after the clamp) zero-reporting the parent's own exclusive time.
            intervals = [
                (parse_dt(c["start_utc"]), parse_dt(c["end_utc"]))
                for c in children_of.get(id(e), []) if c["end_utc"]
            ]
            exclusive = max(0, exclusive - union_duration_ms(intervals))
        out.append({
            "name": e["name"], "parent": e["parent"], "source": e["source"],
            "outcome": e["outcome"], "start_utc": e["start_utc"], "end_utc": e["end_utc"],
            "duration_ms": e["duration_ms"], "exclusive_ms": exclusive,
            "attempt": e["attempt"], "extra": e["extra"],
        })
    out.sort(key=lambda s: parse_dt(s["start_utc"]) or datetime.min.replace(tzinfo=timezone.utc))
    return out, rejected


def fold_into_event(event: dict, project_root, run_id: str) -> dict:
    """Fold this run's spans into ``event['iterate_timings']``.

    Called by ``finalize_iterate`` (F5b), directly beside the existing
    ``phase_timings`` fold. Best-effort + additive: a missing/empty sidecar,
    or any internal error, leaves ``event`` unchanged. Never overwrites a
    pre-existing field. Returns ``event`` for chaining.
    """
    if "iterate_timings" in event:
        return event
    try:
        raw = read_raw_events(project_root, run_id)
        if not raw:
            return event
        valid, rejected = normalize_iterate_timings(raw)
        if rejected:
            print(
                f"[iterate_timings] {len(rejected)} span(s) rejected before persistence: "
                + "; ".join(r["reason"] for r in rejected[:5]),
                file=sys.stderr,
            )
        if valid:
            event["iterate_timings"] = valid
    except Exception as exc:  # noqa: BLE001 — timing must never break finalize
        print(f"[iterate_timings] fold skipped: {exc}", file=sys.stderr)
    return event
