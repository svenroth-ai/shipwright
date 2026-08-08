# Split coverage.fields.<key>.unavailable into not_applicable / missing

Follow-up to ADR-127 (`127-events-context-backfill-keys.md`, PR #602). Filed
as `128` because five spec files already share the number `127`
(`.shipwright/planning/adr/127-*.md`) and `128` was the next unused number
in `.shipwright/planning/adr/` at write time — see F3.md: the sequential
`ADR-NNN` used in `decision_log.md` is assigned later, at
`/shipwright-changelog` release, by `aggregate_decisions.py`; this spec
file's number is only a collision-avoidance prefix for the flat folder.

## Context

`coverage.fields.<key>.unavailable` in `.shipwright/runtime/events-context-
index.json` conflated two different populations: entries that structurally
cannot carry a selection key (`grade_snapshot`, `event_amended`,
`hook_warning`, singletons — none of which ever carry `run_id`/`commit`) and
`work_completed` entries that should carry a key but don't (the commit-
trailer join found no match). Measured on main (831 entries): 352
"unavailable", but only 15 of those have a `run_id` at all; the `work_completed`
population that can actually carry keys was 479/504 = 95% filled. The
conflated envelope reported 58%, which read as a data-quality regression
that was not real.

## Decision

Split each field's `unavailable` bucket into `not_applicable` (no
`run_id`/`commit` linkage at all — the entry cannot structurally carry the
key) and `missing` (linked but the key didn't resolve — actionable).
Eligibility is derived per-entry from `bool(entry["run_id"]) or
bool(entry["commit"])`, never a hardcoded event-type list, so a brand-new
observation-only event type lands in `not_applicable` with zero code
changes (pinned by
`test_unknown_event_type_with_no_linkage_lands_in_not_applicable`). Per-entry
`provenance` (`declared`/`derived`/`unavailable`) is unchanged — the split is
envelope-level only, because a per-row flag cannot report an absent row.
`coverage.missing_work_completed` surfaces the actionable subset (most-recent-
by-log-sequence, capped at 50, `truncated` flagged). `INDEX_SCHEMA_VERSION`
bumped 2→3 to self-invalidate stale caches.

## Rejected alternatives

- **Uniform eligibility across all fields.** Applying the same
  `run_id`/`commit` eligibility test to `supersedes_event_id` produced a
  503-of-831 false "missing" on real repo data — not superseding a prior
  event is the normal state for almost every entry, and there is no
  data-derivable signal for "should have superseded and didn't". Fixed by
  scoping "missing"-eligibility to a field subset,
  `MISSING_ELIGIBLE_FIELDS = {"commit", "changed_files", "affected_frs"}`
  (self-discovered before any review, re-verified against real repo data:
  `supersedes_event_id.missing` is now 0).
- **Including `area_ids` in `MISSING_ELIGIBLE_FIELDS`.** `area_ids` has no
  independent signal — `_event_entry` derives it wholly from
  `changed_files` (`"derived" if paths else "unavailable"`). A matched
  Run-ID commit with a genuinely empty diff resolves `changed_files:
  derived` but `area_ids: unavailable`, even though the trailer join fully
  succeeded — including it re-created the exact false alarm this iterate
  exists to remove. Found by the internal Stage-2 `code-reviewer` (Opus);
  fixed by excluding it, pinned by
  `test_empty_diff_backfilled_commit_does_not_false_flag_area_ids_as_missing`.
- **Lexicographic-by-`event_id` truncation for `missing_work_completed`.**
  The event log is append-only and historical entries can never be
  repaired, so keeping the first 50 alphabetically would bury recent,
  actionable events under an unfixable old backlog. Changed to retain the
  most-recent 50 by log sequence (sorted by `event_id` afterward only for
  deterministic JSON output). Found by the internal Stage-2 reviewer.

## External-Code-Review-Findings (Branch A — openrouter: openai + deepseek)

| # | Severity | Reviewer | Finding | Disposition |
|---|---|---|---|---|
| 1 | low | openai | The split-regression test only used the already-known `grade_snapshot` type; a reintroduced hardcoded event-type list containing `grade_snapshot` would still pass it, despite violating the no-hardcoded-list requirement. | accepted-and-fixed — added `test_unknown_event_type_with_no_linkage_lands_in_not_applicable`, exercising a type the test suite has never referenced before. |
| 2 | high | deepseek | Claimed `aggregate_field_coverage` accesses `entry["sequence"]`, which `_event_entry` allegedly does not populate, causing a `KeyError` at runtime. | rejected-with-reason — false positive. `_event_entry` has populated `"sequence": sequence` since before this diff (confirmed at the merge-base commit, `535d9f93`, line 177); the assignment sits outside every hunk the reviewer's diff excerpt showed. The full suite (42 targeted + 421 `shared/scripts/tests` + 2 `integration-tests`) passed both before and after this review, which would not be possible if the key were absent. |
| 3 | medium | deepseek | Removing the `unavailable` key from `coverage.fields.<key>` may silently break an out-of-repo consumer (dashboard, query tool) still reading the old key. | rejected-with-reason — repo-wide grep found no in-repo consumer keyed on `coverage.fields.<key>.unavailable` (`event_context_query.py` never references `coverage`; the CLI in `event_context.py` dumps the `coverage` dict opaquely without keying into it; the pre-diff `docs/hooks-and-pipeline.md` did not document the old key). `INDEX_SCHEMA_VERSION` bumped 2→3 is exactly this repo's existing self-invalidation mechanism for an envelope-shape change; an out-of-repo consumer (e.g. the separate shipwright-webui repo) is outside this diff's verifiable reach. |
| 4 | low | deepseek | `bool(entry["run_id"])` treats an empty-string `run_id` as ineligible ("ineligible" was mislabeled "misclassified" in the finding); suggested making the intent explicit with `.get(...) not in (None, "")`. | rejected-with-reason — current behavior is already correct: an empty string carries no linkage and should be ineligible, exactly like `None`. No behavior change; the reviewer's own text conceded "which already works". |

## Consequences

Operators reading the coverage envelope now see the real actionable
`work_completed` fill rate instead of a conflated figure; `_score`'s
selection ranking is unaffected (it already excluded unkeyed entries — this
is a reporting-only fix, not a change_type + affected_frs). A future sixth
`PROVENANCE_FIELDS` entry not added to `MISSING_ELIGIBLE_FIELDS` fails safe
(lands `not_applicable`-only) rather than false-alarming, pinned by
`test_missing_eligible_fields_is_a_subset_of_provenance_fields`.
