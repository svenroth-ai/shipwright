#!/usr/bin/env python3
"""Iterate-timing spans — hierarchy resolution, normalization, and the F5b fold.

Sibling of ``iterate_timings.py`` (catalog + writers), ``iterate_timings_pairing.py``
(raw-event pairing + per-entry validation) and ``iterate_timings_synthesis.py``
(parent-containment search + missing-ancestor synthesis) — each split out at
~300 lines (file-size guideline). See ``iterate_timings.py``'s docstring for
the design contract.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone

from lib.iterate_timings import IterateTimingError, SPAN_NAMES, sidecar_path
from lib.iterate_timings_pairing import pair_agent_events, parse_dt, validate_entry
from lib.iterate_timings_synthesis import best_containing_parent, synthesize_ancestor


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
    resolves in rounds against ``by_name`` (seeded with the raw entries,
    growing as ancestors are synthesized):

    - A real (or already-synthesized) instance of any allowed parent name
      that CONTAINS the child -> attach (the containment search tries every
      name the child's span type permits, not just the one it declared —
      "most-recently-opened wins" leniency, unchanged).
    - No containing instance found, but an instance of the child's own
      DECLARED parent name (``e["parent"]``) exists somewhere in the run ->
      "impossible ordering" — a genuine mismatch, rejected, never
      synthesized around. Scoped to the declared name specifically, not the
      union of every name the type allows — a real-but-irrelevant record
      under a merely-permitted sibling name must never suppress synthesis of
      the name actually missing (see ``best_containing_parent``'s docstring).
    - No instance of the declared parent name exists anywhere -> materialize
      the missing ancestor from the envelope of the children that name it
      (see ``iterate_timings_synthesis.synthesize_ancestor``) and retry next
      round. A synthesized ancestor that is itself nested (e.g. a derived
      ``delivery_wait`` still needing ``delivery``) queues for its own
      resolution the same way — bounded by the span catalog's size so a
      logic error can never loop forever.
    """
    by_name: dict[str, list[dict]] = {}
    for e in entries:
        by_name.setdefault(e["name"], []).append(e)

    kept: list[dict] = []
    rejected: list[dict] = []
    unresolved: list[dict] = []
    for e in entries:
        if e["parent"] is None:
            e["_parent_key"] = None
            kept.append(e)
        else:
            unresolved.append(e)

    for _ in range(len(SPAN_NAMES) + 1):
        if not unresolved:
            break
        orphans: list[dict] = []
        for e in unresolved:
            chosen, declared_name_has_record = best_containing_parent(e, by_name)
            if chosen is not None:
                e["_parent_key"] = id(chosen)
                kept.append(e)
            elif declared_name_has_record:
                rejected.append({"reason": f"no containing parent instance for {e['name']!r}", "raw": e})
            else:
                orphans.append(e)
        if not orphans:
            unresolved = []
            break

        # Each distinct missing name synthesizes independently, from only
        # ITS OWN group's children — a known, narrow limitation: if this
        # group's ancestor is itself nested and a DIFFERENT group synthesized
        # in this same round will need to contain it later, this pass has no
        # way to know to widen for it (see iterate-timings.md's "round-
        # batched synthesis" known limitation). Only reachable today via the
        # `delivery` chain and only if deliver_pr.py's own real self-recorded
        # spans are absent; the fallback is rejection, not data corruption.
        by_missing_parent: dict[str, list[dict]] = {}
        for e in orphans:
            by_missing_parent.setdefault(e["parent"], []).append(e)

        next_round = list(orphans)
        synthesized_any = False
        for pname, group in by_missing_parent.items():
            if pname in by_name:
                # Defensive only — every key in `by_missing_parent` came from
                # `orphans`, and an entry only lands there when this round's
                # per-entry pass already found `by_name.get(e["parent"])`
                # falsy for that exact name, so this branch cannot currently
                # trigger. Kept in case a future refactor of the loop above
                # breaks that invariant.
                continue
            synth = synthesize_ancestor(pname, group)
            by_name.setdefault(pname, []).append(synth)
            synthesized_any = True
            if synth["parent"] is None:
                synth["_parent_key"] = None
                kept.append(synth)
            else:
                next_round.append(synth)

        if not synthesized_any:
            # Defensive only — every name in `by_missing_parent` was, by
            # construction, absent from `by_name` a moment ago, so this
            # branch should be unreachable; never leave entries unresolved.
            for e in orphans:
                rejected.append({"reason": f"no containing parent instance for {e['name']!r}", "raw": e})
            unresolved = []
            break
        unresolved = next_round
    else:
        for e in unresolved:
            rejected.append({"reason": f"no containing parent instance for {e['name']!r}", "raw": e})

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
