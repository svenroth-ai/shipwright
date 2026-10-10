# Iterate: release changelog event is committed before the merge

Run: `iterate-2026-10-10-release-event-before-merge` - type: bug - complexity: small.

## Problem
The changelog skill wrote its `phase_completed`/changelog event after the release PR merge and tag push, straight into the main checkout. Nothing committed it, so `shipwright_events.jsonl` stayed dirty on main, a later `git pull --ff-only` could abort, and the release event never reached the event history.

## Change
- Step 7 of the changelog skill records the event BEFORE the merge, commits it by explicit pathspec and pushes it with the release PR (chained with `&&`, so a failure stops the release).
- On main (no PR) the event is recorded before the single `git push --tags origin main`.
- The old post-merge record block is replaced by a pointer; the rationale and scope live in `references/release-workflow.md`.
- `docs/hooks-and-pipeline.md` event row updated; `shared/tests/test_changelog_release_event_before_merge.py` pins the order.

## Out of scope
Other files written after the merge (dashboard, handoff, run-config phase history) are not moved by this change.
