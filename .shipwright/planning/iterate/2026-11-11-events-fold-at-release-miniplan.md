# Mini-plan: events-fold-at-release

## Work breakdown
1. `shared/scripts/tools/fold_events_for_release.py` (new): `fold_for_release(root, base_ref, max_age_days, dry_run)`.
   Layout not `drops` -> `not_applicable`. Base ref does not resolve -> `skipped`. Otherwise `plan_fold` + `apply_fold`
   (the existing fold, unchanged), stage exactly the touched paths, then ONE commit of exactly those paths with
   `git commit --pathspec-from-file=- --pathspec-file-nul` (other staged work stays out; no command-line overflow).
   Always prints one JSON object with a `status`; exit 0.
2. `tools/fold_events.py::_stage` returns the staged paths (was `None`), so the new tool commits what was staged.
3. `plugins/shipwright-changelog/skills/changelog/SKILL.md`: new Step 5.3 before Step 5.4 calling the tool and printing
   at most one summary line.
4. `docs/hooks-and-pipeline.md`: Folding section gets the "fold at release" bullet (cadence = releases).
5. Tests: `shared/tests/test_events_fold_for_release.py` (11 tests on real git repos).

## Failure policy
Housekeeping never stops a release. Conflict, missing base ref, undeletable file, refusing hook: one reported status,
exit 0, release continues. `incomplete` and `commit_failed` leave the tree for a person (the message says how).

## Risks
- A fold commit lands on `main` before the release commit when the release is cut on main (intended: own commit).
- `git commit --only` semantics with a deleted tracked path and a newly added archive: tested.
- Rename detection makes `git show` list the deleted drop and the identical archive as one rename (test uses `--no-renames`).
