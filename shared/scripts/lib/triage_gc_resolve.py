"""Tracked-only resolution for the triage GC engine.

Split out of :mod:`lib.triage_gc_core` (which crossed the 300-LOC guideline
when the Stage-3 doubt-review fix moved ``_resolve_tracked_only`` from a
single file-order pass to the same two-pass ``(ts, file-order)`` resolution
:func:`triage.read_all_items` uses — iterate-2026-08-08-triage-amend-event).
Re-exported from :mod:`lib.triage_gc_core` so every existing importer
resolves unchanged.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make the triage store importable whether invoked from the repo root, via
# `lib.triage_gc_core` (which already does this), or standalone.
_SHARED_SCRIPTS = Path(__file__).resolve().parents[1]
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

import triage  # noqa: E402


def resolve_tracked_only(project_root: Path | str) -> list[dict]:
    """Resolve items from the TRACKED store only (ignore the outbox).

    D1: GC compacts the durable tracked log; the gitignored outbox is the D2
    sweep's concern. Mirrors ``triage.read_all_items`` resolution — append
    first, then status/amend overlaid together ordered by ``(ts, file-order)``
    — but over a single file so GC never touches outbox state. An un-overlaid
    resolution here would make ``plan_gc``'s dry-run report show an amended
    item's PRE-amend title/severity to the operator.

    **Two-pass, not one file-order pass (Stage-3 doubt review, finding 4):** a
    single interleaved pass silently dropped a status/amend that a
    ``merge=union`` churn resolve placed BEFORE its own append on the same
    file — exactly the interleaving ``lib.triage_validate``'s classifier
    already documents as legitimate for this store — and resolved two same-id
    amends in file order instead of ``(ts, file-order)``, which could show the
    WRONG title/severity in the one report this overlay was added to keep
    correct.
    """
    _amend, _flds = triage._load_triage_amend(), triage._load_triage_fields()
    raw_lines = [
        r for r in triage._iter_raw_lines_at(triage._triage_path(project_root))
        if isinstance(r, dict)
    ]

    # Pass 1 — every append establishes a base record.
    resolved: dict[str, dict] = {}
    for raw in raw_lines:
        if raw.get("event") != "append":
            continue
        item_id = raw.get("id")
        if not isinstance(item_id, str):
            continue
        item = {k: v for k, v in raw.items() if k != "event"}
        item["statusBy"] = None
        item["statusReason"] = None
        item[_amend.AMENDED_BY_FIELD] = None
        item[_amend.AMENDED_AT_FIELD] = None
        resolved[item_id] = item

    # Pass 2 — overlay status flips AND amends together, by (ts, file-order):
    # same sort as `triage.read_all_items` — see that function's docstring.
    def _ts_key(raw: dict) -> str:
        ts = raw.get("ts")
        return ts if isinstance(ts, str) else ""

    status_and_amend = [
        (idx, raw) for idx, raw in enumerate(raw_lines) if raw.get("event") in ("status", "amend")
    ]
    status_and_amend.sort(key=lambda t: (_ts_key(t[1]), t[0]))

    for _idx, raw in status_and_amend:
        item_id = raw.get("id")
        if not isinstance(item_id, str) or item_id not in resolved:
            continue
        item = resolved[item_id]
        if raw.get("event") == "amend":
            _amend.try_apply_amend(
                item, raw, severities=_flds.SEVERITIES, kinds=_flds.KINDS,
                priority_from_severity=_flds.suggest_priority_from_severity,
            )
            continue
        if (new_status := raw.get("newStatus")) not in triage.STATUSES:
            continue  # damaged event: skip WHOLE, never half (F26; twin in triage.py)
        item["status"] = new_status
        item["statusBy"] = raw.get("by")
        item["statusReason"] = raw.get("reason")
    return list(resolved.values())
