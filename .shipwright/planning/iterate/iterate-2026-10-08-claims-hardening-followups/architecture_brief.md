# Architecture Brief: claims-hardening follow-ups

## The problem
Four gaps the U5/U6 units recorded as accepted limits: (1) a no-FR label (docs/tooling/...) still covers edits to the requirement catalog because all of `.shipwright/**` counts as bookkeeping; (2) finalize's idempotent re-run returns before the requirement gates; (3) a stacked campaign unit's label is judged against the whole stack, not its own work; (4) surface-evidence freshness ignores hand-resolved merge conflicts and deleted files.

## What already exists
`lib/change_type_paths.py` (per-label globs), `lib/change_type_diff.py` (fork-point diff), `finalize_iterate._record_event`, `verifiers/_surface_revision.py` (branch-write comparison), `lib/_evidence_drop_guard.py` (mtime guard).

## What would newly, permanently exist
One carved-out path pattern; an optional event field `stack_base_ref` (stated by the campaign runner, validated, not derived); a `git merge-tree --write-tree` dependency (git >= 2.38) for conflict replay; a deletion-dating rule.

## Options
- A: Implement all four as described (chosen).
- B: Derive the stack base from campaign loop state instead of a stated field.
- C: Leave (3) fail-closed as today.
- D: Do nothing.

## Constraints
finalize_iterate.py may not grow (bloat cap). Both event-write paths keep identical gates.
