#!/usr/bin/env python3
"""Iterate-timing spans — parent-containment search and ancestor synthesis.

Split out of ``iterate_timings_normalize.py`` at ~300 lines (file-size
guideline), mirroring how that module itself split ``iterate_timings_pairing.py``
out of ``iterate_timings.py``. Private preprocessing helpers for
``_attach_parents`` — not part of the public API other files import — see
``iterate_timings_normalize.py`` and ``iterate_timings.py`` for the design
contract.
"""

from __future__ import annotations

from datetime import timedelta

from lib.iterate_timings import SPAN_PARENTS
from lib.iterate_timings_pairing import parse_dt

_MAX_TIMEDELTA = timedelta.max


def best_containing_parent(e: dict, by_name: dict[str, list[dict]]) -> tuple[dict | None, bool]:
    """Tightest-fitting containing instance for ``e`` among ``by_name``'s
    entries under any of ``e``'s allowed parent names.

    Returns ``(chosen_or_None, declared_name_has_record)``. The second value
    is how ``_attach_parents`` tells "a parent exists but this child doesn't
    fit" (impossible ordering — reject) apart from "no instance of this
    child's OWN declared parent name exists at all" (the trigger for
    ancestor synthesis) — it is scoped to ``e["parent"]`` specifically, NOT
    the union of every name ``SPAN_PARENTS[e["name"]]`` would allow. A span
    whose catalog entry permits more than one parent name (``external_review``/
    ``reviewer_wait``: planning or review; ``ci_wait``: delivery or
    delivery_wait) would otherwise have a real-but-irrelevant record under a
    SIBLING allowed name (e.g. a real, temporally unrelated "planning" span)
    permanently suppress synthesis of the name the child actually named
    ("review") and never has an explicit record of at all — reproducing the
    exact orphaning this function exists to fix, for any run with partial
    agent-mark compliance (found in review). The CONTAINMENT search itself
    still searches the full union below — an open-ended real span under a
    sibling name can legitimately still be the correct container (existing
    "most-recently-opened wins" leniency, unchanged) — only the reject-vs-
    synthesize decision is narrowed to the declared name.
    """
    candidates: list[dict] = []
    for pname in sorted(SPAN_PARENTS[e["name"]], key=lambda p: p or ""):
        candidates.extend(by_name.get(pname, []))
    declared_name_has_record = bool(by_name.get(e["parent"]))
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
    return chosen, declared_name_has_record


def synthesize_ancestor(name: str, children: list[dict]) -> dict:
    """Materialize a missing ancestor span from the envelope (earliest
    start, latest end) of ``children`` — the entries that named ``name`` as
    their own parent but found no explicit record of it anywhere in the run.

    Every producer-owned span in the catalog nests under one of the 7
    top-level groups, but 6 of those 7 are agent-emitted — recorded only if
    the session happens to call the boundary mark. When it doesn't, the
    producer's own real, measured children have nowhere to attach and were
    previously dropped outright (see iterate-timings.md — the P1.17 gap this
    closes). ``source="derived"`` marks the result so it is never mistaken
    for an actual measured boundary: ``_select_top_level`` ranks it below a
    real producer/agent record for the same name, and the throughput report
    labels it explicitly. A real record for ``name``, whenever one exists —
    even an unclosed agent mark — is found by :func:`best_containing_parent`
    before this function is ever called, and always wins.

    Preconditions the caller (``_attach_parents``) guarantees: ``children``
    is non-empty, and every entry already passed ``validate_entry`` (so
    ``start_utc`` is always a parseable string) — this function does not
    re-validate.
    """
    starts = [d for d in (parse_dt(c["start_utc"]) for c in children) if d is not None]
    start_dt = min(starts)
    closed = [c for c in children if c.get("end_utc")]
    if len(closed) == len(children):
        end_dt = max(parse_dt(c["end_utc"]) for c in closed)
        end_utc = end_dt.isoformat()
        duration_ms = max(0, int((end_dt - start_dt).total_seconds() * 1000))
        outcome = "completed"
    else:
        # At least one referencing child is still open — the ancestor's own
        # end is genuinely unknown, not merely unmeasured. Report that
        # honestly as incomplete rather than guessing a boundary from
        # partial data.
        end_utc = None
        duration_ms = None
        outcome = "incomplete"
    non_none = sorted(p for p in SPAN_PARENTS[name] if p is not None)
    # Every name in today's catalog that is ever ITSELF a declared parent
    # (i.e. can reach this function) has at most one non-None candidate —
    # `delivery_wait` -> {"delivery"} is the only nested case. A future
    # catalog addition that names a multi-parent span (like external_review)
    # as someone else's parent would need real disambiguation logic here,
    # not a silent alphabetical pick; fail loud instead.
    if len(non_none) > 1:
        raise RuntimeError(
            f"synthesize_ancestor({name!r}) has {len(non_none)} candidate parents "
            f"{non_none} — needs disambiguation logic, not an arbitrary pick"
        )
    parent = None if None in SPAN_PARENTS[name] else non_none[0]
    return {
        "name": name, "parent": parent, "source": "derived", "outcome": outcome,
        "start_utc": start_dt.isoformat(), "end_utc": end_utc,
        "duration_ms": duration_ms, "attempt": 1, "extra": {},
    }
