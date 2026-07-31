# Iterate Spec: adr-index-churn-register

- **Run ID:** iterate-2026-07-31-adr-index-churn-register
- **Type:** change
- **Complexity:** medium (floor: `cross_component` enforces medium)
- **Status:** draft

## Goal

Close **trg-1acb5304**, the conflict class the previous iterate (#505) created:
`.shipwright/planning/adr/INDEX.md` is now regenerated on a branch, so two
parallel ADR-writing iterates collide on it — and the index is in no
merge-reconciliation register, so `ensure_current` aborts rather than
auto-resolving. Register it and re-derive it from the merged tree.

## Context — why this exists

Before #505, `INDEX.md` changed only on `main`, at release time; a branch never
touched it, so the conflict class did not exist. #505 gave the index two
producers, one of which is iterate F3 — deliberately, so the index row ships in
the same commit as the ADR it points at. The cost of that (correct) decision is
that two branches each adding an ADR now both append at the same anchor.

`INDEX.md` is not in `CHURN_ALLOWLIST` (`shared/scripts/lib/churn_merge.py`) and
has no `merge=union` `.gitattributes` entry, so `classify()` puts it in
`blocking` and the pre-flight gate aborts `ensure_current`, touching nothing.
That fails loudly and safely — no corruption — but it needs a human, and the
whole point of the resolver is that generated artifacts should not.

## Acceptance Criteria

- [ ] **AC1** — A merge conflict on `INDEX.md` is classified `resolvable`, not
      `blocking`, so the pre-flight gate no longer aborts.
- [ ] **AC2** — After the merge, `INDEX.md` is re-derived from the **merged**
      folder listing and staged, so an index carrying rows from *both* sides is
      what gets committed — not either side's pre-merge copy.
- [ ] **AC3** — The re-derive runs on the REAL integration path, which passes
      `only=set()` to `regenerate_tracked_snapshots`. Satisfied by PLACEMENT, not
      by a documented exception: the call lives in
      `integrate_regenerate.regenerate_after_merge`, outside the `only`-scoped
      function entirely, so there is no gate to get wrong.
- [ ] **AC4** — `restore_derived_to_head` does not undo it: the index is not a
      `DERIVED_SNAPSHOTS` member and must survive the post-regen restore.
- [ ] **AC5** — The doc-sync drift guard stays 1:1 — the new allowlist entry
      appears in the `docs/hooks-and-pipeline.md` reconciliation table, in both
      directions.
- [ ] **AC6** — **Integration coverage** (`cross_component`, non-dodgeable): a
      real-scenario test that builds two branches each adding a distinct ADR,
      merges, drives the actual resolver + regenerator, and asserts the committed
      index lists **both** ADRs.

## Spec Impact

- **Classification:** none
- **NONE justification:** Merge-reconciliation machinery only. No FR states a
  promise about `INDEX.md` or about how a churn conflict is resolved; this
  restores the auto-resolution property the resolver already provides for every
  other generated artifact. Behavior-preserving from any requirement's view.

## Out of Scope

- Registering `INDEX.md` in `DERIVED_SNAPSHOTS`. Still the wrong register, for
  the reason #505 gave: that list is for views that are *wrong* when derived on a
  branch, and a folder listing is correct on a branch. `CHURN_ALLOWLIST` is the
  other register — "what the resolver may auto-resolve WHEN a conflict happens" —
  and it is the one this belongs in.
- A `merge=union` `.gitattributes` entry for the index. Union would concatenate
  two sorted lists into an unsorted one with a duplicated header; the index is a
  pure re-derive, so regenerating is both simpler and always correct.

## Design Notes

Resolution strategy is exactly the DERIVED_MD one: take the mainline side at
conflict (`--theirs`, a placeholder), then re-derive from the merged tree in the
follow-up commit. `complete_merge`'s existing `else` catch-all already does the
`--theirs` half for any allowlisted path, so AC1 needs only the registry entry.

The re-derive is the part that needs care (AC3), and where it lives changed
during the build. `regenerate_tracked_snapshots` scopes its work with
`targets = set(DERIVED_MDS) if only is None else set(only)`, and the real caller
passes `only=set()` precisely because an iterate branch no longer carries the
derived snapshots — so anything gated there is never regenerated on the one path
that matters, while every `only=None` unit test still passes.

The first implementation put the call inside that function and documented the
exception. Two things pushed it out. `resolve_churn_conflicts.py` sits at exactly
its ADR-099 bloat ceiling (357), so any addition ratchets an existing exception —
the anti-ratchet hook's stated preference is to shrink, not to bump again. And
the better seam was already there: `integrate_regenerate.regenerate_after_merge`
is *the* post-merge re-derive step, it has room (154 lines, no baseline entry),
and placing the call after `restore_derived_to_head` (and after the
`regenerate_failed` rollback return, so a failed regen never leaves a staged
index) makes AC4 true **by construction** rather than by a comment asserting it. The `only=` trap
disappears rather than being navigated.

**Boundary this creates, stated rather than left implicit:** the manual
`resolve_churn_conflicts.py --mode regenerate` escape hatch does NOT refresh the
index — only the integration path does. That is the path the conflict class
occurs on; an operator running the manual mode can use
`rebuild_adr_index.py --project-root .`, which is the documented command.

## Affected Boundaries

| Producer (writes) | Consumer (reads) | Format |
|---|---|---|
| `lib/adr_index.refresh_best_effort` | `integrate_regenerate.regenerate_after_merge` | Markdown (`INDEX.md`) |
| `lib/churn_merge.CHURN_ALLOWLIST` | `classify()`, `verifiers/silent_revert_detect`, `test_churn_merge_doc_sync` | registry ↔ doc table |

## Confidence Calibration

- **Boundaries touched:** the churn registry ↔ its documented table; the
  resolver's regeneration set; the merge conflict classification.

- **Empirical probes run:**
  - Ran `is_cross_component_change` on the intended file list — returns **True**,
    so the integration-coverage gate applies and AC6 is non-dodgeable.
  - Read `integrate_regenerate.py:71-79`: the real caller passes `only=set()`,
    which is what makes AC3 a real trap rather than a hypothetical.
  - Confirmed `restore_derived_to_head` runs immediately after the regen and
    restores `DERIVED_SNAPSHOTS` only — the index is not a member, so it survives.
  - Confirmed the outbox delivery path works end to end: `trg-1acb5304` was
    written to the main tree's gitignored outbox by the previous run and this
    worktree's setup swept it into tracked `triage.jsonl` (1 line present).

- **Test Completeness Ledger:**

  | # | Testable behavior | Disposition | Evidence / reason_code |
  |---|---|---|---|
  | 1 | INDEX.md conflict classifies resolvable, not blocking (AC1) | tested | test_the_index_is_registered_as_resolvable_churn PASSED |
  | 2 | **INTEGRATION: two parallel ADR iterates both keep their row (AC1+2+3+4)** | tested | test_two_parallel_adr_iterates_both_keep_their_row PASSED (real git, real integrate_main.integrate) |
  | 3 | The merge really conflicted — `--theirs` was taken, not a clean 3-way (AC1) | tested | same test: merge commit index == mainline side |
  | 4 | The committed index is re-derived from the MERGED folder (AC2) | tested | same test: equals the generator output over the merged tree |
  | 5 | The re-derive runs on the real path, which passes only=set() (AC3) | tested | same test would go red if the call were moved back inside regenerate_tracked_snapshots |
  | 6 | The index is not a DERIVED_SNAPSHOTS member, so the restore cannot rewind it (AC4) | tested | test_the_index_is_not_a_derived_snapshot PASSED |
  | 7 | A failed refresh is reported in the run result, not swallowed | tested | test_a_failed_index_refresh_is_reported_not_swallowed PASSED |
  | 8 | The run stays fail-soft (status ok) on a failed refresh | tested | same test, status assertion |
  | 9 | A failed stage leaves no dirty index | tested | test_a_failed_stage_leaves_no_dirty_index PASSED (mutation-verified: replacing the restore with pass turns it RED) |
  | 10 | A failed stage leaves the stale `--theirs` copy, not something else | tested | same test: mainline row present, this branch row absent |
  | 11 | Doc-sync stays 1:1 in both directions (AC5) | tested | test_churn_merge_doc_sync PASSED (4 tests) |
  | 12 | The existing churn classify/dedup/validate rules still hold | tested | test_churn_merge.py 30 PASSED |
  | 13 | The existing resolver + integrate behavior is unchanged | tested | test_resolve_churn_conflicts.py + test_integrate_main.py PASSED |

- **Confidence-pattern check:** Row 2 carries `category: "integration"` — the
  `cross_component` gate. Depth: three review rounds produced 8 + 3 + 3 findings,
  including two that would have shipped silently (a re-derive that never runs on the
  real path; a staged index surviving the rollback). Breadth: 13 behaviors, 0
  untested-testable. The two tests that could pass with the feature reverted were
  found by review and one was deleted rather than patched.

## Verification (medium+)

- **Surface:** cli
- **Runner command:** the resolver driven over a real two-branch merge
- **Evidence path:** `.shipwright/runs/<run_id>/surface_verification.json`
