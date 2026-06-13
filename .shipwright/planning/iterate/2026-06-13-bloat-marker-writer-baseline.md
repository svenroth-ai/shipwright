# Iterate Spec — Align bloat marker writer to the worktree baseline

- **Run ID:** `iterate-2026-06-13-bloat-marker-writer-baseline`
- **Intent:** CHANGE (consistency refactor)
- **Complexity:** medium (locked by `cross_component` safety floor — diff edits `shared/scripts/hooks/*.py`)
- **Spec Impact:** MODIFY (no FR/spec surface; internal hook mechanics)
- **Risk flags:** `cross_component` → integration coverage + full test suite
- **Triage anchor:** `trg-537334f1` (open, P3, kind:improvement) — follow-up to `trg-28e83840`

## Problem

The bloat Stop-gate has two halves:

- **Writer** — `check_file_size.py` PostToolUse hook. On every size crossing it
  upserts a per-session marker entry with `delta` (`anti-ratchet` | `crossing`)
  + `was_in_allowlist`, both derived from one `in_allowlist` bit.
- **Reader** — `bloat_gate_on_stop.py` Stop hook. Re-measures each marked file
  and decides block/pass.

PR #186 (trg-28e83840) fixed the **reader** to resolve a file's ceiling AND its
baseline membership (`in_baseline`) from the *worktree's own*
`shipwright_bloat_baseline.json` when the marker path is a `.worktrees/<slug>/…`
path. The **writer** was left behind: `_write_marker_entry` still computes
`in_allowlist`/`delta`/`was_in_allowlist` against the **MAIN** baseline
(`_baseline_paths(cwd)` where `cwd` is the main repo root), even for a worktree
path. So the writer and reader key the same file off *different* baselines.

### Why it is HARMLESS today (not a safety gap)

In all practical worktree scenarios the reader still reaches the correct verdict
because it recomputes `in_baseline` + `ceiling` from the worktree baseline:

- `delta=="anti-ratchet"` is written only when the stripped path is in MAIN's
  baseline ⇒ it is also in the worktree baseline (worktree branches off main) ⇒
  reader applies the worktree ceiling. Correct.
- `delta=="crossing"` covers both "new ADR exception added in the worktree"
  (reader sees `in_baseline=True` ⇒ grandfather-on-discovery ⇒ pass) and
  "genuinely new" (`in_baseline=False` ⇒ block). The reader distinguishes via
  the recomputed `in_baseline`, not the stored label.
  Proven by `test_worktree_newly_baselined_file_not_treated_as_crossing`.

So this is a **clarity/consistency cleanup**: the marker's `delta`/
`was_in_allowlist` should describe the SAME baseline the reader measures against,
not the stale MAIN baseline.

### Refinement of the triage premise

The triage note offered "drop the now-advisory delta/was_in_allowlist since the
reader recomputes." Code review shows `delta` is **not** droppable — the reader
branches on it to carry *write-time temporal* information (was the file already
grandfathered *before* this session → strict ceiling-check, vs. it crossed
*this* session → grandfather-on-discovery) that the reader cannot reconstruct
from the current baseline alone (both cases have `in_baseline=True`).
`was_in_allowlist` IS dead (never read by the reader) but shares the same
`in_allowlist` bit as `delta`. ⇒ chosen approach = **align the writer**
(option a), which fixes both fields in one change and leaves the carefully-tuned
reader behavior untouched.

## Approach (chosen)

1. **SSoT helper** — add `worktree_root_for(main_root, rel_path)` to
   `shared/scripts/lib/bloat_baseline.py`. Reconstructs the owning worktree root
   from a leading `.worktrees/<slug>/` prefix (or `None` for a main-tree path).
   This is exactly the logic currently duplicated as the reader's private
   `_worktree_root`.
2. **Writer** — `check_file_size._write_marker_entry` resolves the *governing*
   baseline for the path: the worktree's own baseline for a `.worktrees/<slug>/`
   path (MAIN fallback when that baseline is absent/empty), else MAIN. Mirrors
   the reader's `_baseline_for`. `in_allowlist` (hence `delta` +
   `was_in_allowlist`) is now keyed off the same tree the reader measures.
3. **Reader** — replace the private `_worktree_root` with the shared
   `_bb.worktree_root_for` (byte-identical logic; removes the duplication so a
   future change can't drift the two copies).

### Alternative considered (rejected)

- *Drop `delta`/`was_in_allowlist` from the marker.* Rejected: `delta` is
  load-bearing in the reader (see "Refinement" above); dropping it would force
  the reader to pick a single behavior for `in_baseline=True` entries, breaking
  either `test_grandfathered_crossing_passes` or `test_blocks_on_anti_ratchet`.

## Behavioral impact

Behavior-preserving in the normal flow: when a file crosses *before* being added
to the worktree baseline (the usual edit-then-baseline order), both old and new
writers record `delta="crossing"` because the file is in neither baseline at
write time. The only divergence is the unusual baseline-first-then-grow order,
where the new writer records `anti-ratchet` and the reader correctly applies the
worktree ceiling — which matches the CI anti-ratchet gate (the authority).
Existing writer unit tests (`test_recorder_classifies_worktree_baselined_file_as_anti_ratchet`,
`test_marker_*` in `test_hooks.py`) keep passing via the MAIN fallback.

## Acceptance Criteria

- **AC-1:** `worktree_root_for` exists in `lib/bloat_baseline.py`, returns the
  owning worktree root for a `.worktrees/<slug>/…` path and `None` for a
  main-tree path; idempotent/backslash-tolerant (delegates to existing
  `normalize_path`/`strip_worktree_prefix`).
- **AC-2:** Writer records `delta="anti-ratchet"`/`was_in_allowlist=true` for a
  file present in the *worktree* baseline but absent from MAIN's; `"crossing"`
  for a file in neither.
- **AC-3:** Reader behavior unchanged — `_worktree_root` removed, all
  `bloat_gate_on_stop` + worktree-baseline tests still pass.
- **AC-4 (integration / cross_component):** an end-to-end test drives the REAL
  writer (`_write_marker_entry`) to produce the marker against a worktree-only
  baseline, then the REAL Stop gate (subprocess) to consume it — proving the two
  components compose: a file at its worktree ceiling does NOT block; the same
  file grown past the worktree ceiling DOES block.

## Confidence Calibration
- **Boundaries touched:** the bloat marker JSON contract
  (`bloat_pending.<sid>.json`) between the PostToolUse writer and the Stop
  reader; the `shipwright_bloat_baseline.json` baseline read in both halves.
- **Empirical probes run:** (1) traced every writer/reader path combination
  (MAIN-only / worktree-only / both / neither baseline) by hand and confirmed
  the reader's verdict is unchanged for all normal cases — see "Behavioral
  impact"; (2) confirmed `is_cross_component_change` matches `hooks/.+\.py$` ⇒
  cross_component is real, not prose-only; (3) confirmed `was_in_allowlist` has
  zero readers via `grep`.
- **Test Completeness Ledger:** see the table below — every changed behavior is
  `tested`; 0 testable-but-untested.
- **Confidence-pattern check:** depth — writer + reader + shared helper all
  unit-tested; breadth — MAIN-only, worktree-only, neither, and grow-past-ceiling
  cases covered; **integration composition** — AC-4 adds a `category:"integration"`
  behavior driving the real writer→reader pipeline (satisfies the non-dodgeable
  `check_integration_coverage` gate).

### Test Completeness Ledger (preview — machine block recorded at F5)

| Behavior | Disposition | Evidence |
|---|---|---|
| `worktree_root_for` reconstructs/`None` (AC-1) | tested | new unit tests in `test_bloat_marker_worktree_aware.py` |
| writer keys delta off worktree baseline (AC-2) | tested | new writer unit test (worktree-only baseline ⇒ anti-ratchet) |
| writer MAIN fallback preserved | tested | existing `test_recorder_classifies_worktree_baselined_file_as_anti_ratchet` + `test_marker_*` |
| reader uses shared helper, behavior intact (AC-3) | tested | existing `test_bloat_gate_on_stop` + `test_bloat_gate_worktree_baseline` suites |
| writer→reader compose on worktree-only baseline (AC-4) | tested (category=integration) | new end-to-end test (real writer + real Stop-gate subprocess) |
