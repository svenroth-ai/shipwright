"""Aggregate coverage.fields.* + coverage.missing_work_completed over already-
built event_context_index entries.

Split out of event_context_index.py (iterate-2026-08-08-coverage-envelope-
split) once that file crossed the 300-line guideline. Per-entry provenance
(declared/derived/unavailable) is computed by ``_event_entry`` in
event_context_index.py and stays there; this module only aggregates.
"""

from __future__ import annotations

from typing import Any

#: Cap on coverage.missing_work_completed.event_ids -- an aggregate summary
#: list, not a per-row field; see iterate-2026-08-08-coverage-envelope-split.
MAX_MISSING_WORK_COMPLETED_IDS = 50

#: Fields where a well-formed entry always has a value once eligible -- an
#: eligible-but-empty commit/changed_files means the git-trailer join failed
#: to find its match, and eligible-but-empty affected_frs means the entry
#: declared neither an FR list nor a change_type (the FR-gate requires one of
#: the two). Two fields are deliberately excluded:
#:
#: - `area_ids` has NO independent signal -- it is derived wholly from
#:   `changed_files` (`provenance["area_ids"] = "derived" if paths else
#:   "unavailable"`), so a matched commit with a genuinely EMPTY diff (an
#:   `--allow-empty` Run-ID commit) resolves `changed_files: derived` but
#:   `area_ids: unavailable` even though the join succeeded completely.
#:   Including it here re-created the exact false alarm this iterate exists
#:   to remove (code review, iterate-2026-08-08-coverage-envelope-split);
#:   wherever area_ids is legitimately missing, changed_files already says so.
#: - `supersedes_event_id`: NOT superseding a prior event is the normal,
#:   correct state for the overwhelming majority of entries, and there is no
#:   data-derivable signal that distinguishes "legitimately nothing to
#:   supersede" from "should have recorded a supersession and didn't" --
#:   treating its absence as `missing` produced a 503-of-831 false alarm on
#:   real repo data (iterate-2026-08-08-coverage-envelope-split).
MISSING_ELIGIBLE_FIELDS = frozenset({"commit", "changed_files", "affected_frs"})


def aggregate_field_coverage(entries: list[dict[str, Any]], fields: tuple[str, ...]) -> dict[str, Any]:
    """Return ``{"fields": {...}, "missing_work_completed": {...}}`` for `entries`.

    `fields.<key>` splits each field's `unavailable` population into
    `not_applicable` (no run_id/commit linkage at all -- an observation-type
    event structurally cannot carry the key) and `missing` (a linked change
    record whose key is still empty -- actionable). Eligibility is derived
    from the entry's own data (a run_id or an already-resolved commit), never
    a hardcoded event-type list, so a new observation-only event type lands in
    not_applicable without a code change. `missing` counts the eligible
    population across ALL event types (including unrepairable pre-FR-gate
    history); `missing_work_completed` is the narrower, directly-actionable
    subset -- the `event_type == "work_completed"` entries among them, most-
    recent-first and capped.
    """
    field_coverage = {field: {"derived": 0, "declared": 0, "not_applicable": 0, "missing": 0} for field in fields}
    missing_work_completed: list[tuple[int, str]] = []
    for entry in entries:
        eligible = bool(entry["run_id"]) or bool(entry["commit"])
        has_missing_field = False
        for field in fields:
            status = entry["provenance"][field]
            if status == "unavailable":
                bucket = "missing" if (eligible and field in MISSING_ELIGIBLE_FIELDS) else "not_applicable"
                has_missing_field = has_missing_field or bucket == "missing"
            else:
                bucket = status
            field_coverage[field][bucket] += 1
        if has_missing_field and entry["event_type"] == "work_completed":
            missing_work_completed.append((entry["sequence"], entry["event_id"]))
    # Keep the MOST RECENT entries (by log sequence) under the cap -- the log
    # is append-only and historical entries can never be repaired, so a
    # lexicographic-by-id cap would bury recent, actionable events under an
    # unfixable backlog of old ones. Sort the retained slice by event_id for
    # deterministic JSON output.
    missing_work_completed.sort(key=lambda item: item[0], reverse=True)
    kept = sorted(event_id for _, event_id in missing_work_completed[:MAX_MISSING_WORK_COMPLETED_IDS])
    return {
        "fields": field_coverage,
        "missing_work_completed": {
            "count": len(missing_work_completed),
            "event_ids": kept,
            "truncated": len(missing_work_completed) > MAX_MISSING_WORK_COMPLETED_IDS,
        },
    }
