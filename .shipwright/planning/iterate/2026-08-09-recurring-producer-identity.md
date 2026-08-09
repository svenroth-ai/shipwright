# Iterate: recurring producer identity

- **Run ID:** iterate-2026-08-09-dismissed-recurring
- **Status:** implemented
- **Intent:** bug
- **Complexity:** medium (shared triage writer plus rolling producers)
- **Authoritative card:** `trg-5deee0f9` from the main worktree outbox. It is not
  tracked in `origin/main`; that fetched base contains only the dismissed,
  superseded `trg-c8073edd`.
- **Spec impact:** NONE — restores durable operator decisions for internal triage
  producers; no numbered product requirement changes.

## Root-cause investigation

- **Observed:** The idempotent writer treated terminal states as absent. A
  recurring producer that found the same logical condition after a dismissal or
  promotion therefore minted a new card ID.
- **Reproduction:** Create an item, dismiss or promote it, then emit the same
  source/dedup-key condition. Before this change a new append was written.
- **Boundary:** The scan already resolves the tracked-store and outbox union,
  but terminal records were excluded from its suppression rule.
- **Root cause:** The durable condition identity was source + dedup key (and,
  where requested, commit), while the duplicate rule admitted only active or
  parked records.

## Acceptance criteria

1. Prior logical conditions are found across the tracked store and outbox, for
   every status, using source + dedup key and the producer's commit-match policy.
2. An unchanged condition after an operator dismissal or promotion does not
   mint a new ID; the original item remains the canonical decision trail.
3. A material change (a different dedup key, or a commit change when that
   producer matches commits) produces a separate item.
4. A condition automatically resolved by its own rolling producer can regress
   under the original ID without turning an operator decision into permanent
   global silence.
5. Apply the identity/reopen rule to the required-check drift race producer and
   both phase-quality and compliance rolling action units, preserving their
   status preconditions and residence behavior.
6. Cover dismissed, promoted, parked, material-change, resolved/regressed,
   tracked/outbox-union, and concurrent producer execution behavior.

## Mini-plan

1. Make matching terminal records durable in the shared idempotent writer while
   preserving the existing source/dedup/commit identity policy.
2. Let phase-quality and compliance reopen only their own auto-dismissed rolling
   item under the canonical lock; a matching active or operator-terminal item
   blocks that reopen.
3. Keep the F0 required-check race producer attached to its durable condition
   handle, then verify producer composition, union behavior, and concurrency.

## Alternative considered

- Add a condition-fingerprint field. Rejected because source + dedup key already
  encodes the material condition and the existing item ID preserves its history.

## Confidence calibration

- **Boundaries touched:** shared triage store; phase-quality, compliance, and
  F0 required-check producers.
- **Explicit non-scope:** W3 test-evidence freshness and the PR pending-check
  path. No fresh captured API payload reproduced a pending-check defect.
- **Test Completeness Ledger:**
  - AC-1 **tested** —
    `test_a_dismissal_living_only_in_the_outbox_suppresses_too` and
    `test_a_park_living_only_in_the_outbox_suppresses_too`.
  - AC-2 **tested** —
    `test_dismissed_standing_producer_item_is_not_refiled`,
    `test_promoted_item_stays_durable_for_its_matching_commit`, and
    `test_promoted_backlog_is_not_reopened_by_an_unchanged_failure`.
  - AC-3 **tested** —
    `test_materially_changed_standing_condition_is_a_new_item` and the
    different-commit half of `test_promoted_item_stays_durable_for_its_matching_commit`.
  - AC-4 **tested** —
    `test_auto_resolved_backlog_reopens_under_its_original_id` (phase quality)
    and `test_auto_resolved_backlog_reopens_under_its_original_id` (compliance).
  - AC-5 **tested** —
    `test_a_race_after_the_operator_closed_the_card_keeps_that_decision` and
    `test_operator_terminal_duplicate_blocks_auto_reopen`.
  - AC-6 **tested** —
    `test_idempotent_concurrency_under_lock` and
    `test_concurrent_regression_reopens_one_original_backlog`, alongside the
    dismissed/promoted/parked/material/union cases named above.
- **Confidence-pattern check:** direct storage, union resolution, auto-reopen,
  producer composition, and concurrent producer execution are covered. No UI
  or network surface exists for this internal CLI/store behavior.

## Verification (medium+)

- **Surface:** cli
- **Runner:** focused pytest producer and triage suites; final F0/F0.5 evidence
  is captured in the run artifact before delivery.