# Mini-Plan — capture dirtiness before the producer writes

Run: `iterate-2026-08-01-grade-snapshot-dirty-capture` · Complexity: medium

## Problem statement

`grade_snapshot` cannot say whether the tree it graded held uncommitted source.
Measuring at emit time is wrong because the producer has already written tracked
files by then (measured: `dirty=true` on a pristine tree). A dirty flag built this
way was withdrawn before commit after two review rounds; an exclusion list hung off
`DERIVED_SNAPSHOTS` was rejected in the same review.

## Chosen approach — capture at producer entry, inherit through the environment

> **Revised after external review.** The first draft carried the capture in a
> run-scoped JSON store. Gemini's reducibility finding was accepted and the store
> was dropped; dispositions for all nine findings are in
> `iterate-2026-08-01-grade-snapshot-dirty-capture/external-plan-review.md`.

A `capture_dirty(project_root, run_id)` leaf with **first-capture-wins** semantics.
Producers call it at entry, before their first write. It records the result in
`os.environ` (`SHIPWRIGHT_SOURCE_DIRTY` + `SHIPWRIGHT_SOURCE_DIRTY_RUN`); later
askers in the same run — including subprocesses, which inherit the environment for
free — read the captured value instead of re-measuring.

Why this shape:

- It answers the right question. `dirty` is a property of the tree the grade was
  computed **from**; the producer's writes are its output. Capturing at entry makes
  the field mean what a consumer thinks it means.
- **First-capture-wins is what makes it composable.** `update_compliance` calls
  `capture_dirty` unconditionally at its own entry and is correct whether it was
  invoked standalone (it measures) or from `finalize_iterate` (it reads the earlier
  capture). No caller has to know who else is in the stack.
- It crosses the process boundary that parameter-threading cannot:
  `update_compliance` is launched as a **subprocess** — and it does so without an
  `env=` argument at any spawn site, so a parent's obligation is one line.
- The measurement cannot perturb itself: nothing is written to the tree at all.

## Alternative considered — a run-scoped JSON store

`.shipwright/runs/<run_id>/source_state.json`, beside the `main_tree_snapshot.json`
that `setup_iterate_worktree` already writes there.

**Rejected on reducibility.** Its only capability the environment lacks is reaching
a process that is *not a descendant* of the capturer — and that consumer was
measured not to exist: `emit_grade_snapshot` has exactly one caller, and no hook or
shell script invokes `update_compliance`. To serve no reachable case it would have
had to carry five defensive mechanisms the review correctly demanded of it — atomic
exclusive create against a concurrent writer, path-safe run-id validation (a run id
would otherwise reach a filesystem path), containment against symlink escape,
tree-identity binding, and a versioned schema. *Simplicity First*: the boring shape
wins, and each of those five findings dissolved with the store rather than needing
an answer.

Kept from it: the argv seam. `update_compliance` gains `--run-id` so the binding
survives the spawn; explicit `--run-id` beats `SHIPWRIGHT_RUN_ID`.

## Steps

1. **TDD `source_state_capture.py`** — tests first: first-capture-wins (AC1),
   cross-process round-trip (AC2), no-run-id path (AC3), corrupt store (AC4).
2. **`grade_snapshot_shape`** — `dirty` parameter, stamped when known and omitted
   when not (AC5); `dirty` added to `ATTRIBUTION_KEYS` (AC6).
3. **Wire producers** — `finalize_iterate` (before Step 1), `update_compliance`
   (entry + `--run-id`), `_grade_snapshot`, `record_event` CLI.
4. **Boundary probe** — reproduce the pristine-tree `dirty=true` defect against the
   old path, then prove `dirty=false` on the new one (AC7).
5. **Docs** — `docs/hooks-and-pipeline.md` consumer contract (AC8).
6. **Review cascade** + finalization F0–F12.

## Risks

- **A stale export in a long-lived operator shell** could be honoured by a later,
  unrelated run. Mitigated by the run-id binding: the value is read only when
  `SHIPWRIGHT_SOURCE_DIRTY_RUN` matches the reader's own run id.
- **A parent that writes before spawning and does not capture** silently reverts to
  the old late measurement. Measured: of the four spawning parents only
  `finalize_iterate` writes first, and it is wired. The sibling-process residual in
  a pipeline run is named in the spec's Out-of-scope.
- **Never raise into a producer.** Every failure in the capture path degrades to
  `None` (unknown) and the field is then omitted, matching the emitter's
  "attribution never fails the caller" posture.
