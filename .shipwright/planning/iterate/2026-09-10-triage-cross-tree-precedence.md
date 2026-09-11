# Iterate Spec: triage-cross-tree-precedence

- **Run ID:** iterate-2026-09-10-triage-cross-tree-precedence
- **Type:** bug
- **Complexity:** medium
- **Status:** draft

## Goal
`triage.read_all_items`'s cross-tree fold-in (`lib.triage_cross_tree`) lets a
foreign (sibling-worktree) `status` event outrank a status this tree already
decided on its own tracked+outbox union, purely because the foreign event
carries a later timestamp and today's pass-2 sort has no origin precedence.
Measured on `trg-74ef24ce`: two abandoned worktrees
(`.worktrees/p2-59-branch-feedback-authority-redo`,
`.worktrees/token-cost-controllable`, both unmerged, no commit since
2026-08-09/10) each carry a stale `status -> triage` event dated 2026-08-09/10
that outranks the 2026-07-28 `dismissed` events already on `origin/main`,
resurrecting a dismissed card as open. Fix: a foreign `status` event applies
only when this tree's own tracked+outbox union has no `status` event at all
for that id — local decisions can never be overruled by a sibling, foreign
events still fill gaps for ids this tree has never decided. `amend` events are
unaffected (title/detail only, no status) and keep pure-chronological
ordering, matching the existing module boundary.

## Acceptance Criteria
- [x] AC1: a local `status` event for an id at T1, and a foreign `status`
  event for the same id at T2 > T1, resolves the LOCAL status regardless of
  which timestamp is later.
  (`test_a_chronologically_later_foreign_status_cannot_override_a_local_decision` PASSED)
- [x] AC2: a foreign `status` event for an id this tree's tracked+outbox union
  has never decided still resolves that foreign status (gap-fill preserved —
  `test_a_dismiss_recorded_only_in_a_worktree_resolves_as_dismissed_on_main`
  stays green).
- [x] AC3: `amend` events (local or foreign) keep pure chronological
  `(ts, file-order)` resolution — unaffected by the new precedence rule.
  (`test_a_foreign_amend_still_resolves_purely_chronologically_even_when_the_id_has_a_local_status`,
  `test_a_local_and_foreign_amend_tie_still_resolves_by_file_order_not_origin` PASSED)
- [x] AC4: the existing tie-break test asserting a foreign event wins an exact
  timestamp tie against a LOCAL decision for the same id
  (`test_a_foreign_tie_is_broken_by_file_order_not_origin`) is corrected to
  assert the new, intended behavior (local wins outright — no tie to break,
  since local-decided ids never consult the foreign side at all).
  (renamed/rewritten as `test_a_local_status_wins_an_exact_timestamp_tie_against_a_foreign_status` PASSED)

## Spec Impact
- **Classification:** none
- **ADD:** none
- **MODIFY:** none
- **REMOVE:** none
- **NONE justification:** this restores the board's own documented intent —
  a decision already on `origin/main` must be authoritative over a sibling's
  stale, undelivered reopen. No FR describes cross-tree fold-in precedence;
  the governing prose lives in `lib/triage_cross_tree.py`'s own module
  docstring and `triage.read_all_items`'s docstring, both updated in this
  diff to describe the corrected rule.

## Out of Scope
- The WebUI TypeScript composer (`triage-compose.ts`) lives in the separate
  `shipwright-webui` repo (not vendored here since v0.4.0) — porting the same
  precedence rule there is filed as a follow-up triage card, not fixed here.
  **Clarification (external review, openai):** this is not a NEW divergence
  this fix introduces. Per the bug report, that composer sources
  `[local-tracked, origin, local-outbox]` with **no foreign tail at all** —
  it already disagrees with the Python `read_all_items` (which folds in
  sibling logs) both before and after this fix. What this fix changes is
  that the Python side now agrees with the WebUI board more often, not less:
  for any id this tree has already decided (the common case), the Python
  reader now shows the same locally-decided status the WebUI always showed;
  the residual disagreement is narrowed to the gap-fill case (an id this
  tree has never decided, where Python still folds in a sibling's decision
  and the WebUI still does not) — unchanged by this iterate either way.
- The full fan-out/parse cost (91 sibling logs / ~84k foreign records parsed
  per read, no cross-process cache) stays out of scope, per
  `lib/triage_cross_tree.py`'s own prior doubt-review disposition — a bounded
  fix needs a `git` subprocess or a persistent cache, both explicitly
  rejected before. This fix's precedence check does cheaply skip *applying*
  a foreign status event once an id is known locally-decided (no extra
  parsing avoided, but no wasted sort/apply work either).
- No expiry / merged-branch detection for abandoned worktrees — unchanged
  design constraint (this module never shells out to git).

## Design Notes
n/a — no UI surface, pure resolution-logic fix in `shared/scripts/`.

## Affected Boundaries
| Producer (writes) | Consumer (reads) | Format |
|---|---|---|
| `lib/triage_cross_tree.foreign_status_and_amend_records` | `triage.read_all_items` pass 2 | in-process list[dict] (not itself a serialized-file boundary; the underlying `.shipwright/triage.jsonl` boundary is unchanged by this fix) |

Not a new `touches_io_boundary` risk — no serialized format is added or
changed; only in-process precedence changes.

## Internal Plan Review (opus-plan-reviewer)
- **Ran:** yes
- **Severity:** medium
- **Summary:** Precedence rule and the rejected lower-layer-filtering
  alternative are architecturally sound, but the plan under-specified
  validity-filtering for the new local-status-ids gate and the test list had
  a concrete outbox-only-decision gap.
- **Findings:**
  1. (medium, architecture) local-status-ids gate must filter by
     `newStatus in STATUSES` (mirrors pass 2's own tolerant-skip and
     `lib.triage_delivery.foreign_undelivered_from_records`'s parallel
     filter) — otherwise a malformed local status record permanently blocks
     a legitimate foreign gap-fill. **fix** — integrated; added
     `test_a_malformed_local_status_event_does_not_block_a_legitimate_foreign_gap_fill`.
  2. (medium, completeness) no test exercised a local decision living only
     in the outbox (not yet swept to tracked) blocking a foreign override —
     the exact D1 union path the fix claims to cover. **fix** — integrated;
     added `test_a_local_decision_in_the_outbox_only_still_blocks_a_foreign_override`.
  3. (low, architecture) `format_pending_delivery_notice`'s wording predates
     this precedence asymmetry and may now read as implying a locally-decided
     item could still flip from a sibling event, when it structurally
     cannot without a real merge. **disclose** — not a blocker; filed as a
     follow-up triage card alongside the two already-planned out-of-scope
     items (Out of Scope section).
  4. (low, performance) flagged a risk of reading local tracked+outbox files
     twice if the local-status-ids set were computed from a fresh read.
     **decline (no change needed)** — verified the implementation already
     reads local lines exactly once (`local_lines`) and reuses that same
     list to build both `local_status_ids` and the merged `raw_lines`; no
     second read exists.
- **Known limitations:** `format_pending_delivery_notice` wording staleness
  (finding 3) — follow-up triage card, not fixed here.
- **Status:** 2 fixed, 1 disclosed, 1 declined (no change needed)

## External LLM Review
- **Providers:** glm (openrouter), openai (codex) — both succeeded.
- **Verdicts:** glm=revise · openai=revise (no `high`-severity findings from
  either — proceeded without an operator STOP per protocol).
- **Findings integrated (fix):**
  1. (glm/openai, medium) mini-plan text didn't explicitly spell out the
     `newStatus in STATUSES` validity filter on the local-decided-ids gate —
     already implemented in code/tests from the internal review pass, but
     the mini-plan wording was updated to match.
  2. (glm, medium) the two internal-review-driven regression tests weren't
     listed in the mini-plan's file list/work breakdown — added.
  3. (glm, low) multiple foreign `status` events for a never-locally-decided
     id — added `test_multiple_foreign_status_events_for_a_never_decided_id_still_resolve_chronologically`.
  4. (openai, medium) an exact-timestamp local+foreign `amend` tie — added
     `test_a_local_and_foreign_amend_tie_still_resolves_by_file_order_not_origin`.
- **Disclosed (not fixed here):**
  5. (glm, low) consolidate the `format_pending_delivery_notice` wording
     staleness (plan-review finding 3) and the WebUI TS parity item into one
     follow-up triage card — done at Step 5 (mini-plan work breakdown item
     6).
  6. (openai, medium) WebUI/Python dual-reader consistency during the gap
     before the WebUI is ported — addressed as a clarification in this
     spec's Out of Scope section: not a new divergence, and net-improved for
     the common (already-decided) case by this fix.

## Architecture Review
- **Brief:** `.shipwright/planning/iterate/iterate-2026-09-10-triage-cross-tree-precedence/architecture_brief.md`
- **Verdicts:** glm=approve · openai=approve
- **Smallest thing that would do (per reviewers):** as proposed — gate
  foreign `status` application on the id being absent from the local
  status-id set; `amend` untouched.
- **Findings:** none blocking. glm noted the alternative of deleting/expiring
  abandoned worktrees is an operational workaround, not a durable fix — the
  spec's Out of Scope section already agrees (no git-subprocess expiry, by
  the module's own existing design constraint).
- **Reconciliation:** no divergence from the mini-plan's proposed approach —
  both reviewers confirmed it is the smallest fix, and neither surfaced an
  alternative to reconcile against.

## Confidence Calibration
- **Boundaries touched:** none new (see Affected Boundaries).
- **Empirical probes run:**
  - Reproduced the exact measured defect against un-patched code: a local
    dismiss + a chronologically-later foreign reopen resolved `triage`
    (wrong) before the fix, `dismissed` (correct) after — confirmed RED then
    GREEN.
  - Reproduced the old (buggy) exact-timestamp-tie test against un-patched
    code to confirm it was actually exercising the flaw, not incidental
    behavior — confirmed it asserted the WRONG winner before the fix.
  - opus-plan-reviewer (internal plan review) probe: found the
    local-decided-ids gate needed a `newStatus in STATUSES` validity filter
    — confirmed by writing a malformed-local-status test that failed without
    the filter and passed with it.
  - External review (glm+openai) probe: found the multi-foreign-event and
    exact-timestamp-amend-tie cases were unasserted — both now covered and
    passing.
- **Test Completeness Ledger:**

  | # | Testable behavior | Disposition | Evidence / reason_code |
  |---|---|---|---|
  | 1 | Local status at T1 always wins over a chronologically-later foreign status at T2>T1 for the same id | tested | `test_a_chronologically_later_foreign_status_cannot_override_a_local_decision` PASSED |
  | 2 | Local status wins an exact-timestamp tie against a foreign status (no tie to break) | tested | `test_a_local_status_wins_an_exact_timestamp_tie_against_a_foreign_status` PASSED |
  | 3 | Foreign status still fills a gap for an id with no local status event | tested | `test_a_dismiss_recorded_only_in_a_worktree_resolves_as_dismissed_on_main` PASSED |
  | 4 | A local decision living in the OUTBOX only (not yet tracked) still blocks a foreign override — D1 union | tested | `test_a_local_decision_in_the_outbox_only_still_blocks_a_foreign_override` PASSED |
  | 5 | A malformed local status event (invalid `newStatus`) does not block a legitimate foreign gap-fill | tested | `test_a_malformed_local_status_event_does_not_block_a_legitimate_foreign_gap_fill` PASSED |
  | 6 | `amend` (local or foreign) stays purely chronological even when the id has a local status decision | tested | `test_a_foreign_amend_still_resolves_purely_chronologically_even_when_the_id_has_a_local_status` PASSED |
  | 7 | A local+foreign `amend` exact-timestamp tie still resolves by file order (unaffected by the new rule) | tested | `test_a_local_and_foreign_amend_tie_still_resolves_by_file_order_not_origin` PASSED |
  | 8 | Multiple foreign status events for a never-locally-decided id still resolve chronologically among themselves | tested | `test_multiple_foreign_status_events_for_a_never_decided_id_still_resolve_chronologically` PASSED |
  | 9 | A foreign append never seeds an item this tree never created (pre-existing guarantee, unaffected) | tested | `test_a_foreign_append_never_seeds_an_item_this_tree_never_created` PASSED (regression guard) |
  | 10 | `read_all_items` composes the local reader and the cross-tree sibling reader end to end (integration) | tested (category:integration) | `test_read_all_items_composes_local_and_sibling_stores_for_ids_never_locally_decided` PASSED |
  | 11 | A foreign status event with a non-string (unhashable) id does not crash the read — external code review (glm) crash-guard finding | tested | `test_a_foreign_status_with_a_non_string_id_does_not_crash_the_read` PASSED |

  0 untested-testable rows.
- **Confidence-pattern check:** Asymptote (depth) — yes: the internal plan
  review's "are you confident the plan is complete?" pass produced two real
  findings (STATUSES filter, outbox-only test gap), so one more probe
  (external review) was run before F0, which itself produced two further
  findings (multi-foreign-event ordering, amend-tie), both now covered.
  Coverage (breadth) — every ledger row is `tested`; 0 untested-testable;
  `cross_component`'s Integration Coverage requirement is met by row 10.
