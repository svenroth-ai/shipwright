# Bloat exception — `shared/scripts/lib/autonomous_loop.py` raised to 454-LOC

<!-- Named by run_id per `_template-bloat-exception.md` — this heading does
     NOT claim a numeric ADR-NNN; that identity is assigned later, at
     release, by decision_log.md. `shipwright_bloat_baseline.json`'s entry
     for this file is set to `"state": "exception", "adr": "ADR-pending:
     .shipwright/planning/adr/iterate-2026-09-22-r2-worktree-capability-autonomous-loop-bloat.md"`. -->

- **Status:** accepted
- **Date:** 2026-09-22
- **Re-Review-Date:** 2026-12-22
- **Incident Reference:** `iterate-2026-09-22-r2-worktree-capability`
  (campaign-dag-scheduler R2), delegated Stage-2 code review at
  campaign-mode.md step 3f-bis. The limit was crossed fixing a real,
  high-severity correctness bug the review found: R2's own lease heartbeat
  (`lib.unit_lease.touch_unit_lease`) writes `branch` onto a unit's
  `loop_state.json` row from Step 1, before any commit exists. That made
  `_reconcile_in_progress`'s pre-existing branch-has-commits heuristic
  reachable, on any campaign-session resume, for a unit that is genuinely
  still building — silently marking it falsely `complete` with no
  `result.json`, dropping it from the campaign with no rebuild and no PR.

## Context

`autonomous_loop.py` was already grandfathered at 436/300 lines before this
change (no prior exception ADR — this is its first). Two rounds landed here:

1. A first fix (**436 -> 446**) gated `_reconcile_in_progress`'s
   branch-has-commits guess on lease STALENESS (`is_unit_lease_stale`).
2. The delegated doubt-reviewer (Stage 3, campaign-mode.md 3f-bis) disproved
   it: gating on staleness only defers the false-completion bug past
   `DEFAULT_STALE_AFTER_SECONDS` (7200s) — a resume happening AFTER that
   window (the common case, not the exotic one) hits the exact same bug, and
   a live-lease unit was left silently `in_progress` forever with no other
   path back to `pending` (nothing downstream of `cmd_init` reconciles it).
   The second round (**446 -> 454**) replaces staleness with PROVENANCE: once
   a row has EVER been lease-touched (`lease_touched_at` present), the
   branch-has-commits guess never applies to it again, live or expired,
   falling straight through to the pending-reset instead — removing the
   trigger condition rather than narrowing its window. The same round also
   wraps `cmd_init`'s existing-state read-modify-write in the same
   `loop.lock` every other `loop_state.json` writer already uses (a
   pre-existing gap the lease's own live heartbeat made load-bearing).

This is a correctness fix for a bug R2 itself introduced the trigger
condition for; leaving it unfixed and shipping R2 anyway would hand the
campaign loop a live, load-bearing false-completion (or, after the first
attempted fix, false-silent-stall) path for every future sub-iterate that
crashes after its first commit.

## Ousterhout Argument

`_reconcile_in_progress` is the single place `cmd_init` decides whether an
`in_progress` unit found on a resumed campaign is done, abandoned, or still
running. That decision has always depended on external evidence (a
`result.json`, or a git-log comparison) with no way to ask "is anyone still
actually working on this" — R2's lease is exactly that signal, already
computed by an existing exported predicate (`is_unit_lease_stale`) that had
no consumer yet. Wiring it into the one function whose entire job is this
decision keeps the interface narrow (one added guard clause, one import) and
resolves an existing ambiguity in the reconciliation logic itself rather
than working around it at a caller.

## YAGNI Check

- The guard clause is load-bearing today, not speculative: it fires exactly
  when R2's own live lease-touch wiring (Step 1, before Step 4, before Step
  5 — already shipped in this same PR) has left `branch` set on an
  `in_progress` row, which is true for every sub-iterate in every campaign
  from this PR onward, not a hypothetical future case.
- No broader refactor of the reconcile function was attempted — only the one
  branch this bug actually reaches is touched; the `result.json`-present
  fast path and the no-lease-fields fallback are byte-identical to before.

## Chesterton-Fence Check

The existing `result.json`-first check stays first and unconditional — a
genuinely finished unit is still reconciled the same way regardless of lease
state, so this fence is preserved. The branch-has-commits heuristic and the
`pending`-reset fallback are not removed, only gated behind "the lease has
actually gone stale (or never existed)" — the exact condition under which
they were originally sound (no lease existed at all until this same PR).

## Decision

Raise `current` for `shared/scripts/lib/autonomous_loop.py` from **436 to
454**, `state: "exception"`, `adr: "ADR-pending:
.shipwright/planning/adr/iterate-2026-09-22-r2-worktree-capability-autonomous-loop-bloat.md"`,
in the same commit as the fix. The companion regression coverage lives in a
new, separate, under-budget test file
(`shared/tests/test_autonomous_loop_lease_reconcile.py`) rather than
`shared/tests/test_autonomous_loop.py` (itself already grandfathered at
442/300) so no second file needed its own bump for this change.

**Retirement plan.** Re-review at 2026-12-22 whether R4's fencing work
(claim/attempt tokens) subsumes this heuristic entirely — if a unit's
liveness becomes fencing-verifiable rather than guessed from git history,
`_reconcile_in_progress`'s branch-has-commits path (and this guard clause
alongside it) may be removable outright rather than merely gated.

## Consequences

- `_reconcile_in_progress` may grow further before the anti-ratchet blocks
  again (454-line current). Not a licence to keep growing — the next
  crossing needs its own ADR.
- A unit that has EVER been lease-touched is now reset to `pending` (attempt
  bumped) by `cmd_init` whenever no `result.json` exists for it, live lease
  or not — this is a deliberate trade: it can restart a build that was, in
  fact, still healthily running at resume time (a rare window: the
  orchestrator session that would still be driving that Task has, by
  definition, just been restarted). That restart is bounded and observable
  (a normal retried attempt), unlike the false-complete/silent-stall failure
  modes it replaces, which were unbounded and silent.
- `cmd_init`'s reconcile branch now takes `loop.lock` — a resumed campaign
  session's `cmd_init` can briefly block on a concurrently-heartbeating
  runner's `touch_unit_lease`, and vice versa. Both already used bounded
  30s timeouts; no new deadlock class, since neither ever calls the other.

## Rejected alternatives

- **Gate on lease staleness instead of provenance (the first attempt).**
  Rejected after the doubt-reviewer disproved it: skipping the heuristic only
  while `is_unit_lease_stale(unit)` is False defers the false-complete bug
  past the 7200s lease horizon rather than removing its trigger, and the
  common resume case (an operator resuming a campaign the next day) is
  exactly past that horizon. It also left a live-lease unit silently
  `in_progress` with no other reconciliation path, which `cmd_next` and
  `cmd_finalize` both treat as "does not exist" — a campaign could finalize
  as `all_complete` with that unit never built.
- **Rename the lease's `branch`/`attempt` fields to a `lease_`-prefixed
  namespace instead of touching `autonomous_loop.py`.** Rejected: R3's own
  spec (`sub-iterates/R3-review-diff-fix.md`) already commits to reading
  `worktree`/`branch`/`attempt_id` by these exact names off `loop_state.json`
  rows for its `check_review_attribution.py` fallback resolution; renaming
  now would only move the same field-collision risk into R3 instead of
  fixing it, and would require rewriting a spec for a sub-iterate not yet
  built.
- **Fix only `unit_lease.py`'s `attempt` write and leave `branch` alone.**
  Rejected: the `attempt`-only fix (also applied, no bloat impact — see this
  run's decision-drop) does not address the false-completion risk, which
  comes entirely from `branch`'s presence during `in_progress`, not from
  `attempt`.
- **Leave the bug for a future sub-iterate to fix.** Rejected: R2 is what
  makes the bug reachable in production for the first time; shipping it
  live and unfixed for even one more sub-iterate risks silently losing R3's
  own work on the next campaign-session interruption.
