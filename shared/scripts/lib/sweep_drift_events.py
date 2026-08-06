"""Pure line-shape predicates for the main-tree drift adoption.

A NEUTRAL LEAF, the same reasoning as :mod:`lib.sweep_text` / :mod:`lib.jsonl_records`
/ :mod:`lib.sweep_gc`: these are stdlib-only, git-free and I/O-free, they are what
:mod:`lib.sweep_drift`'s refusal rules are expressed in, and splitting them keeps that
module under the 300-LOC guideline it shares with the rest of the sweep family.

:mod:`lib.sweep_drift` re-exports :func:`append_ids_of`, so existing importers keep
resolving.
"""

from __future__ import annotations

import json

from lib.jsonl_records import split_records

__all__ = ["append_ids_of"]


#: Producer event kinds a drift line may carry. Anything else is not a line this module
#: is willing to move (and therefore not one it is willing to delete from the log either).
_EVENTS = frozenset({"append", "status"})


def append_ids_of(lines: list[str]) -> frozenset[str]:
    """Ids of every well-formed ``append`` event in ``lines``, recovering record boundaries.

    Only valid appends enter the universe (external review): a fragment that does not
    decode, a non-object, or a non-``str`` id contributes nothing — none of those may
    protect a status from the orphan check.

    RECORD-BOUNDARY RECOVERY (iterate-2026-08-06-triage-validate-deadends, Stage-2 code
    review finding 1). This is the PROTECTION universe: an id present here stops a
    ``status`` being read as an orphan and quarantined away. The per-physical-line
    ``json.loads`` it used to do therefore failed in the DESTROYING direction — an append
    committed on local main inside a line glued by an unterminated write vanished from the
    universe, so the operator's dismiss for it became an unprotected orphan, was
    quarantined, and the item resurrected once main reached origin. That is the
    composition of the two defects this run fixes (a glued line × an append only local
    main has), and the validator recovering such a line while this did not is exactly the
    disagreement the run exists to remove.

    Widening this universe is monotonically SAFE: an extra id can only PREVENT a
    quarantine, never cause one. Adoption stays deliberately line-granular and
    conservative — ``_is_producer_event`` still refuses a glued line, so the sweep
    refuses to MOVE one rather than re-serializing it.
    """
    ids: set[str] = set()
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        records, _remainder = split_records(stripped)
        for obj in records:
            iid = obj.get("id")
            if obj.get("event") == "append" and isinstance(iid, str):
                ids.add(iid)
    return frozenset(ids)


def _parsed(line: str) -> dict | None:
    if not line.strip():
        return None
    try:
        obj = json.loads(line)
    except (json.JSONDecodeError, ValueError):
        return None
    return obj if isinstance(obj, dict) else None


def _is_producer_event(line: str) -> bool:
    """True iff ``line`` is a well-formed triage producer event (append / status with a
    str id) — the only shape adoption is willing to move."""
    obj = _parsed(line)
    return bool(obj) and obj.get("event") in _EVENTS and isinstance(obj.get("id"), str)


def _is_header(line: str) -> bool:
    obj = _parsed(line)
    return bool(obj) and obj.get("schema") == "triage" and "v" in obj
