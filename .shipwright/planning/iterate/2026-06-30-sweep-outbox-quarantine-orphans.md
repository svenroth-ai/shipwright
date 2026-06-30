# Iterate — change: quarantine orphan-status in the triage outbox sweep

**Run-ID:** iterate-2026-06-30-sweep-outbox-quarantine-orphans
**Intent:** change · **Complexity:** medium · **Risk:** cross_component
**Spec Impact:** NONE (behavior-preserving for the valid path; adds a recovery path that was previously a hard failure)

## Problem

`shared/scripts/lib/sweep_outbox.py::sweep_outbox_to_branch` materializes
`combined = worktree-tracked-triage (= origin/main) ∪ outbox`, deduplicates, and runs
`churn_merge.validate_triage_text`. That validator errors when any `status` event's
`id` has **no `append` anywhere** in the combined set (the reader silently drops such
orphans, so the validator fail-closes). On ANY error the sweep returns
`status="invalid"` and delivers **nothing** — stranding every legitimate pending
append in the gitignored outbox.

Observed 2026-06-30: 15 orphaned dismiss events (appends lost when a local fold commit
was orphaned by a release rebase; one self-inflicted by dismissing an item whose append
was still uncommitted main-tree drift) blocked delivery of 15 real findings for days.
The failure is silent (a fail-soft WARN at `setup_iterate_worktree`).

## Decision

Make the sweep **quarantine** outbox-originating orphan-status lines instead of
hard-blocking the whole buffer:

1. Classify the combined log: collect `orphan_status_ids` (status with no append) and
   whether any **non-orphan** error exists (bad/missing header, duplicate append,
   invalid JSON, empty log).
2. If there is a non-orphan error → **`status="invalid"`** unchanged (fail-closed for
   genuine corruption; do NOT quarantine — leave the outbox untouched, preserving the
   existing "invalid → don't touch outbox" invariant).
3. Else, if `orphan_status_ids` is non-empty: identify the **outbox** lines that are
   status events with an id in `orphan_status_ids`. Trial-remove them and re-validate
   the remainder. Only if the remainder is clean: append them (wrapped with
   `quarantined_at` / `reason` / `original`) to
   `.shipwright/triage.outbox.quarantine.jsonl` (durable atomic write, under the same
   `_FileLock`), drop them from the outbox working set, and continue normal delivery.
4. Surface `quarantined` (count) on `SweepResult`; ensure the outbox file is rewritten
   when quarantine removed lines even if GC dropped nothing.

Only **outbox**-originating orphans are quarantined; a worktree-tracked/origin-side
orphan the sweep cannot rewrite still hard-blocks (re-validate catches it).

## Files
- `shared/scripts/lib/churn_merge.py` — add `classify_triage_text(text) -> TriageValidation`
  (`errors`, `orphan_status_ids`, `has_non_orphan_error`); `validate_triage_text` keeps its
  string-list API (re-expressed in terms of the classifier — same outputs).
- `shared/scripts/lib/sweep_outbox.py` — quarantine branch in `sweep_outbox_to_branch`;
  `_quarantine_path()` + `_append_quarantine()`; `SweepResult.quarantined`; outbox-rewrite
  on `(gc_dropped or quarantined)`.
- `.gitignore` — ignore `.shipwright/triage.outbox.quarantine.jsonl`.
- Tests — `shared/tests/test_churn_merge.py`, `shared/tests/test_sweep_outbox*.py` (+ helper).

## Acceptance Criteria
- AC1: outbox orphan-status → quarantined to the quarantine file, valid remainder
  delivered to the branch, `SweepResult.quarantined == N`, those lines removed from the outbox.
- AC2: non-orphan corruption (dup append / bad header / invalid JSON) → `status="invalid"`,
  nothing quarantined, outbox untouched.
- AC3: mixed orphan + non-orphan corruption → `status="invalid"` (corruption wins), outbox untouched.
- AC4: orphan-status in the worktree-tracked log only (not outbox) → not quarantined; re-validate
  still fails → `invalid` (documented; sweep cannot rewrite origin).
- AC5 (integration, real git): end-to-end sweep with a seeded outbox orphan + a real pending
  append delivers the append to the branch and writes the quarantine file.

## Confidence Calibration
- **Boundaries touched:** `.shipwright/triage.outbox.jsonl` (read/trim), new
  `.shipwright/triage.outbox.quarantine.jsonl` (write), worktree-tracked `triage.jsonl`
  (read-only), the `iterate/<slug>` branch commit. `touches_io_boundary` (jsonl producer/consumer).
- **Empirical probes run:** (filled at build) reproduce orphan-block on a real-git fixture →
  observe `invalid`; apply change → observe `committed` + quarantine file.
- **Test Completeness Ledger:** (filled at F5) every AC → `tested` with evidence; AC5 carries
  `category:"integration"`.
- **Confidence-pattern check:** depth = re-validate-after-trim proves no residual orphan;
  breadth = orphan-only / corruption-only / mixed / origin-side / integration;
  composition = real-git integration sweep proves churn_merge ↔ sweep_outbox compose.
