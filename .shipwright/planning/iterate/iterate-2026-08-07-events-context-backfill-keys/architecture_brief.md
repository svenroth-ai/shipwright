# Architecture Brief: events-context-backfill-keys

## The problem

A disposable index (`events-context-index.json`, 815 entries) is meant to let
tooling select "relevant" past events by matching changed files, area, and
requirement id. Most entries have those fields empty (roughly 77-96% empty
depending on the field), so nothing can be ranked by relevance today — any
ordering built on top of this index is effectively fiction. The fields are
empty because they are currently read verbatim off each recorded event's own
JSON, and most recorded events don't carry them directly.

## What already exists here

- A git commit convention already stamps a `Run-ID:` line in every commit
  footer, and a compliance-plugin script already reads that one trailer back
  off a given commit sha.
- A separate, already-populated catalogue maps file paths to project areas
  via pattern matching, with an existing matcher function.
- A separate module already answers "which recorded changes touched
  requirement X" by reading the same event log this index is built from.
- The index-building code already re-derives its output from scratch on
  every relevant change (it explicitly treats itself as disposable/cache,
  not a source of truth).

## What would newly, permanently exist

A backfill step inside the existing index-building code that, once per
build, walks the project's git history to recover the missing fields for
events that don't carry them directly, plus a small new shared module that
reads that history. Going forward, commits would also carry a couple of
additional structured lines (beyond the one that already exists) so future
events have more to recover from without needing git history at all. Once
built, this needs no separate operator attention — it runs automatically
every time the index rebuilds, the same as it does today.

## Options on the table

- **A:** Recover the missing fields from git history and an existing
  catalogue/matcher inside the current index-building code, so every rebuild
  self-heals; add a couple of new structured lines to future commits so
  newer events increasingly don't need the git-history recovery at all.
- **B:** Only add the new structured commit lines going forward; leave
  historical events with empty fields as-is (no git-history recovery).
- **C:** Do nothing — leave the index as-is and treat the "relevance"
  feature built on top of it as not yet viable.

## Constraints that are not negotiable

none
