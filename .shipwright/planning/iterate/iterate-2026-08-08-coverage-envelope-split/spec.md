# iterate-2026-08-08-coverage-envelope-split — spec context

Follow-up bug report to #602 (events-context backfill keys). Small-complexity
BUG iterate — no formal iterate spec.md is produced at this complexity tier;
this file exists solely to give the external code-review cascade the same
requirements text an operator would read.

## Problem

`coverage.fields.<key>.unavailable` in `.shipwright/runtime/events-context-
index.json` conflates two different populations: entries that structurally
cannot carry a selection key (observation-type events — `grade_snapshot`,
`event_amended`, `hook_warning`, singletons — which never carry `run_id`/
`commit`) and entries that should carry a key but don't (a `work_completed`
record whose commit-trailer join found no match). Measured on main (831
entries): 352 "unavailable", but only 15 of those have a `run_id` at all —
the other 337 have no join key to begin with. The `work_completed` population
that CAN carry keys is 479/504 = 95% filled; the conflated envelope reported
58%, which is not a real data-quality problem.

## Do

- Split `coverage.fields.<key>.unavailable` into `not_applicable` (entry
  structurally cannot carry the key) and `missing` (it should and doesn't).
- Derive eligibility from the entry's own data (presence of `run_id` /
  `commit`), never a hardcoded event-type list — a new observation-only
  event type must land in `not_applicable` without a code change.
- Keep the split at envelope (aggregate) level — a per-row flag cannot
  report an absent row; per-entry `provenance` vocabulary stays unchanged.
- Surface genuinely missing `work_completed` entries so they're actionable
  (`coverage.missing_work_completed`).
- Add a test pinning the split so the two buckets cannot collapse back
  into one.

## Do not

- Backfill the observation-type records (`grade_snapshot`, `event_amended`,
  `hook_warning`, singletons) — they are records of an observation, not a
  change, and inventing `changed_files` for them would be fabricating data.
- Change the selection logic — `_score` already excludes unkeyed entries
  from ranking, so they cannot win budget slots. This is a reporting fix
  only.

## Constraint

Follow-up to ADR-127 (`127-events-context-backfill-keys.md`); five ADR files
currently share the number 127 — do not mint a new ADR-127, check the
highest ADR number in use first.
