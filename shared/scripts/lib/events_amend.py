"""Shared SSOT: apply ``event_amended`` corrections to the event log.

An ``event_amended`` entry carries ``amends`` (the target event id) and
``fields`` (a dict overlaid onto the target via ``{**target, **fields}``).
Applying drops the amendment entries themselves and merges their fields onto
the matching target events, so every consumer — ``config``/``record_event``,
the change-history collector, and the detective audit (group_d) — honors
corrections identically.

Deliberately self-contained (no intra-package imports) so the detective audit
can load it via ``audit_adapters.load_shared_lib`` without polluting the
``lib`` namespace.
"""

from __future__ import annotations

from typing import Any


def apply_amendments(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Overlay ``event_amended`` fields onto their target events.

    Amendment entries are removed from the result; their ``fields`` merge onto
    the event whose ``id`` matches ``amends`` (last amendment wins per target).
    """
    amendments: dict[Any, dict] = {}
    for e in events:
        if e.get("type") == "event_amended":
            amendments[e.get("amends")] = e.get("fields", {})

    result: list[dict[str, Any]] = []
    for e in events:
        if e.get("type") == "event_amended":
            continue
        if e.get("id") in amendments:
            e = {**e, **amendments[e["id"]]}
        result.append(e)
    return result
