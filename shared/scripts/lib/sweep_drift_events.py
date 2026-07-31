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

__all__ = ["append_ids_of"]


#: Producer event kinds a drift line may carry. Anything else is not a line this module
#: is willing to move (and therefore not one it is willing to delete from the log either).
_EVENTS = frozenset({"append", "status"})


def append_ids_of(lines: list[str]) -> frozenset[str]:
    """Ids of every well-formed ``append`` event in ``lines``.

    Only valid, unambiguous appends enter the universe (external review): a line that does
    not parse, is not an object, or carries a non-``str`` id contributes nothing — it must
    never protect a status from the orphan check.
    """
    ids: set[str] = set()
    for line in lines:
        obj = _parsed(line)
        iid = obj.get("id") if obj else None
        if obj and obj.get("event") == "append" and isinstance(iid, str):
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
