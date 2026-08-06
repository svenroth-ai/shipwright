"""Canonical form of one triage line — the equivalence rule the outbox GC compares on.

Split from :mod:`lib.sweep_gc` so the "when are two lines the same record?" question
is one readable leaf, separate from "what does the GC do about it".

The rule exists because the GC used to ask two different questions — an ``append``
was delivered iff its ``id`` was in origin (content ignored, so a refreshed record
was destroyed: audit finding 14) and everything else iff its raw text was (so any
re-serialization made a line permanently un-GC-able: finding 27).

**Supported equivalence is exactly** object key order, insignificant whitespace and
Unicode escaping. Three input classes are deliberately EXCLUDED, each because it
would let two materially different lines share one canonical form and so be dropped
in place of one another:

* duplicate object keys — ``json.loads`` keeps only the last;
* any float literal — binary floats are many-to-one from source text (overflow,
  underflow and rounding all collide);
* anything that is not a JSON object at all.

Each excluded line falls back to exact raw-text membership, which is the fail-safe
side: it can only be dropped when origin holds it byte-for-byte.

:func:`canonical_form`, the only public function here, is TOTAL: it never raises,
for any input. The two ``_reject_*`` hooks raise DELIBERATELY — that is the whole
mechanism — and ``canonical_form`` is the only place that calls them, absorbing
both. That is not a style preference: this code runs inside the sweep's canonical
triage lock and on the ``setup_iterate_worktree`` step-5 path, where an escaping
exception aborts setup after ``git worktree add`` has already succeeded, leaving an
orphaned worktree. A hook call moved outside its ``try`` would be a real regression.
"""

from __future__ import annotations

import json


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict:
    """``object_pairs_hook`` that refuses a JSON object carrying a duplicate key.

    Plain ``json.loads`` keeps only the LAST of a duplicate key, so
    ``{"id":"A","ts":"T1","ts":"T2"}`` and ``{"id":"A","ts":"T2"}`` would parse —
    and canonicalize — identically. Two materially different lines would then match
    and the GC would drop one of them: precisely the loss this module exists to
    prevent (external plan review). A duplicate-key document is therefore treated as
    NOT canonicalizable and falls back to text membership, where it can only be
    dropped on an exact byte match.
    """
    seen: dict[str, object] = {}
    for key, value in pairs:
        if key in seen:
            raise ValueError(f"duplicate JSON key {key!r}")
        seen[key] = value
    return seen


def _reject_float(raw: str) -> float:
    """``parse_float`` / ``parse_constant`` hook that refuses every float literal.

    See :func:`canonical_form` for why floats are excluded. Raising here is the whole
    mechanism: the caller catches ``ValueError`` and the line degrades to raw text.
    """
    raise ValueError(f"float literal {raw!r} is not canonicalizable")


def canonical_form(stripped: str) -> str | None:
    """The canonical serialization of ``stripped``, or ``None`` if it has none.

    ``None`` means "match this line by raw text instead" and is returned for
    anything that is not an unambiguous JSON object: unparseable text, a bare
    scalar (valid JSON but not a record — callers do ``raw.get(...)``), a
    duplicate-key object, a float-bearing object, or input that defeats the encoder.

    **The supported equivalence boundary is exactly**: object key order,
    insignificant whitespace, and Unicode escaping (``\\u00e9`` == ``é``).

    **Any float literal makes a line non-canonicalizable.** Binary floats are a
    many-to-one map from source text, and the collision lands in the DROP
    direction: ``1e400`` and ``1e999`` both parse to ``inf``, ``1e-400`` and
    ``0.0`` both parse to ``0.0``, and ``1.0`` collides with anything else that
    rounds to it. Two materially different lines would share one canonical form and
    the GC would drop a line origin does not hold — the same class as the
    duplicate-key hazard, pointing the dangerous way. A first attempt closed only
    the overflow tail with ``allow_nan=False`` and left underflow and rounding open;
    rejecting the whole float type is what actually makes the boundary total. The
    triage record schema carries no numeric fields, so no real record is affected,
    and the degraded path is fail-safe: exact raw-text membership.

    TOTAL by contract: never raises, for any input. See the module docstring for why
    an exception here is not survivable.
    """
    try:
        obj = json.loads(
            stripped,
            object_pairs_hook=_reject_duplicate_keys,
            parse_float=_reject_float,
            parse_constant=_reject_float,
        )
    except (TypeError, ValueError, RecursionError):
        # TypeError: ``json.loads`` rejects a non-str/bytes argument. Today the only
        # caller passes ``str``, but the contract above is absolute, so the two
        # handlers stay symmetric rather than relying on caller discipline.
        return None
    if not isinstance(obj, dict):
        return None
    try:
        return json.dumps(
            obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        )
    except (TypeError, ValueError, RecursionError):
        return None
