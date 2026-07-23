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


def _deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    """Recursively overlay ``overlay`` onto ``base`` (both dicts).

    A key that is a dict in BOTH is merged recursively; any other ``overlay``
    value replaces ``base``'s. Returns a new dict — neither input is mutated.
    """
    out = dict(base)
    for k, v in overlay.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def apply_amendments(
    events: list[dict[str, Any]], *, deep: bool = False,
) -> list[dict[str, Any]]:
    """Overlay ``event_amended`` fields onto their target events.

    Amendment entries are removed from the result; their ``fields`` merge onto
    the event whose ``id`` matches ``amends`` (last amendment wins per target).

    ``deep`` (default ``False``): the merge is SHALLOW — a nested object in
    ``fields`` REPLACES the prior value wholesale, so ``{"tests": {"passed": 5}}``
    silently drops sibling keys such as ``tests.e2e_run`` / ``tests.skipped``.
    Pass ``deep=True`` to merge nested dicts recursively, so an amendment
    correcting one sub-field preserves the untouched siblings. The default stays
    shallow for byte-identical back-compat with every existing caller.
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
            overlay = amendments[e["id"]]
            e = _deep_merge(e, overlay) if deep else {**e, **overlay}
        result.append(e)
    return result
