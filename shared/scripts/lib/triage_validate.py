"""Triage-log validation + failure classification (pure; no git / no IO).

Extracted from :mod:`lib.churn_merge` (iterate-2026-06-30-sweep-outbox-quarantine-orphans)
so the triage validator stays a small, single-source cluster and ``churn_merge``
stays under the 300-LOC guideline. ``churn_merge`` re-exports these names, so the
historical ``from lib.churn_merge import validate_triage_text`` import path is
unchanged.

:func:`classify_triage_text` is the single source of truth; :func:`validate_triage_text`
is a thin projection that returns only the string-error list (its historical API).
The added structure lets the outbox sweep distinguish the *recoverable* orphan-status
class (a ``status`` whose id has no ``append`` anywhere — the reader silently drops it)
from genuine corruption (bad/missing header, duplicate append, invalid JSON, empty log).
"""

from __future__ import annotations

import json
from dataclasses import dataclass


@dataclass(frozen=True)
class TriageValidation:
    """Structured result of :func:`classify_triage_text`.

    ``errors`` — the full string-error list (identical to the historical
    :func:`validate_triage_text` output, same order). ``orphan_status_ids`` — ids
    whose ONLY defect is a ``status`` event with no ``append`` anywhere (the
    recoverable class the outbox sweep can quarantine). ``has_non_orphan_error`` —
    True if any error OUTSIDE that class exists (bad/missing header, duplicate
    append, invalid JSON, empty log); genuine corruption a caller must treat as fatal.
    """

    errors: list[str]
    orphan_status_ids: frozenset[str]
    has_non_orphan_error: bool


def classify_triage_text(text: str) -> TriageValidation:
    """Validate the triage log AND classify its failures (orphan-status vs other).

    Checks: (a) the first non-blank line is the ``{"schema":"triage",...}`` header;
    (b) every non-blank line parses as JSON; (c) no duplicate ``append`` for one id;
    (d) no ``status`` event whose id has no ``append`` anywhere. Error strings + their
    order are unchanged from the historical validator, so :func:`validate_triage_text`
    is a faithful projection.
    """
    errors: list[str] = []
    orphan_ids: set[str] = set()
    header_seen = False
    has_other = False
    append_ids: set[str] = set()
    status_ids: list[tuple[int, str]] = []
    for n, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append(
                f"line {n}: not valid JSON ({exc.msg}) — union may have corrupted a historic line"
            )
            has_other = True
            continue
        if not header_seen:
            header_seen = True
            if not (isinstance(obj, dict) and obj.get("schema") == "triage" and "v" in obj):
                errors.append(
                    f"line {n}: first non-blank line is not the triage header "
                    '({"v":...,"schema":"triage",...}) — the merge reordered or dropped it'
                )
                has_other = True
            continue
        if not isinstance(obj, dict):
            continue
        event, iid = obj.get("event"), obj.get("id")
        if event == "append":
            if iid in append_ids:
                errors.append(f"line {n}: duplicate append for id {iid!r} — the merge double-counted an item")
                has_other = True
            append_ids.add(iid)
        elif event == "status":
            status_ids.append((n, iid))
    # Second pass: status ids are checked against the FULL append set, NOT only
    # appends seen earlier in file order — ``merge=union`` may legitimately
    # interleave lines so a status precedes its append while both are present
    # (order-sensitive validation would false-fail `triage_invalid`). Only a
    # status whose append is absent ANYWHERE is a real merge drop.
    for n, iid in status_ids:
        if iid not in append_ids:
            errors.append(f"line {n}: status for id {iid!r} has no append anywhere — the merge dropped it")
            if isinstance(iid, str):
                orphan_ids.add(iid)
    if not header_seen:
        errors.append("triage log is empty after merge — the header was dropped")
        has_other = True
    return TriageValidation(
        errors=errors,
        orphan_status_ids=frozenset(orphan_ids),
        has_non_orphan_error=has_other,
    )


def validate_triage_text(text: str) -> list[str]:
    """Return a list of error strings (empty = valid) for the triage log.

    Thin projection of :func:`classify_triage_text`. Output (strings + order) is
    unchanged from before the classifier extraction; existing callers
    (``reconcile_triage``, ``sweep_outbox``, …) are unaffected.
    """
    return list(classify_triage_text(text).errors)
