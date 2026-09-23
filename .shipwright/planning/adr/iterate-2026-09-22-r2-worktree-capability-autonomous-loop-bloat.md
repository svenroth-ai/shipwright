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

### Round 2 growth (442 -> 469)

Campaign `campaign-dag-scheduler` R4's own Stage-3 doubt review (4 HIGH + 1
medium + 2 low against PR #790) landed two fixes in `cmd_finalize`/
`cmd_record`, both hardening existing responsibilities of this dispatcher,
not new ones:

- **HIGH #1:** `cmd_finalize`'s `kind == "sub_iterate"` dispatch (added
  after this file's original 442-line baseline) called the new, strict
  `sub_iterate_finalize_summary` unconditionally, refusing ANY non-TERMINAL
  unit with no compatibility path for a row still carrying pre-R4 legacy
  vocabulary — live production risk for every campaign not yet touched by
  R4's atomic-claim flow. Fixed by gating that dispatch on `any(u.get(
  "attempt_id") for u in state["units"])` (the SAME compatibility boundary
  `loop_state.resolve_record_status`/`enforce_record_fencing` already use),
  falling through to the untouched legacy branch below otherwise.
- **LOW #1:** `cmd_record`'s mutation write-loop used an exact-match `--unit`
  lookup while its own fencing pre-check (`enforce_record_fencing`, via
  `find_unit_row`) is case-fold-aware — a case-mismatched but genuinely
  existing unit id passed the fence and then silently found nothing in the
  write loop, still reporting `{"recorded": true}` / exit 0. Fixed by
  switching the `kind == "sub_iterate"` mutation lookup to `find_unit_row`
  too (`kind == "section"` keeps its original exact-match lookup, unchanged)
  and hard-failing (exit 3) when even that finds nothing.

### Round 3 growth (469 -> 491)

Scoped orchestrator-level re-review of Round 2's own HIGH #1 fix found a
real gap in the compatibility gate, plus one further instance of Round 2's
own LOW #1 defect class it had not covered — both hardening, not new
responsibilities:

- **Gate-mixing gap:** Round 2's `any(u.get("attempt_id"))` gate is an OR
  over units, but `sub_iterate_finalize_summary`'s own refusal is an AND —
  a campaign straddling the R5a flip (some units finished under the old
  serial path with no `attempt_id`, others claimed by the new atomic-claim
  flow) routed into the strict branch anyway and refused finalize forever,
  since nothing promotes a legacy `"complete"` row into the 9-state
  vocabulary post-hoc. Fixed by additionally requiring `all(u["status"] in
  STATES for u in state["units"])` before trusting the strict branch; a
  mixed campaign now falls through to the legacy branch below, exactly
  pre-R4 behaviour and therefore never worse.
- **LOW #1's remaining instances:** the case-fold fix only reached
  `cmd_record`'s success-path write loop; its non-JSON-result and
  contract-violation failure branches still used the same exact-match
  lookup Round 2 fixed elsewhere, so a case-mismatched unit id could still
  pass the fencing pre-check and then silently fail to be marked `failed`.
  Fixed with the identical `find_unit_row`-when-`sub_iterate` pattern
  Round 2 already established, at both remaining sites.

### Round 4 growth (491 -> 514)

External Tier-3 review (GPT, PR #790 round 21) found `cmd_record`'s two
`runs_dir_for` call sites both unguarded for the `ValueError` that helper
raises on a charset-rejected id (round 9 of the sibling
`iterate-2026-09-22-r4-state-mechanics-loop-state-bloat.md`): the
non-JSON-result fallback lookup passes raw, unvalidated `args.unit`
straight through, and the success-path `result.json` write passes an
already state-matched row's `unit["id"]` — canonical, but still reachable
from a hand-edited/corrupted `loop_state.json`, the exact threat model
round 19 of that same sibling ADR already fixed for
`lib.loop_state._reconcile_legacy`. Either site previously crashed the
whole CLI with an uncaught traceback on a malformed id instead of this
function's own structured-failure shape. Fixed by wrapping both calls:
the fallback lookup treats a `ValueError` the same as "no fallback
available" (falls through to the existing non-JSON structured-failure
path, exit 3); the success-path write returns a controlled `{"recorded":
false, ...}` response and exit 3 without ever calling `_save_state` — the
in-memory mutations already applied to that block are discarded, never
persisted. Not a new responsibility — closing the same gap round 9/19
already closed elsewhere, for the two call sites in this module that had
been missed. Two new regression tests, in a new file (not the sibling
`test_autonomous_loop.py`, already `"state": "grandfathered"` at 442
lines — growing a grandfathered file needs converting it to a filed
`exception` first, not a bare bump):
`test_autonomous_loop_record_runs_dir_safety.py`.

### Round 5 growth (514 -> 539)

External Tier-3 review (GPT, PR #790 round 23) found `cmd_record`'s third
`handoff_dir_for` call (the handoff-path lookup right after the round-4
`result.json` write) and `cmd_finalize`'s own `handoff_dir_for` call both
unguarded for the same `ValueError`. Independently verified before fixing:
the `cmd_record` site is passed the exact same `state["loop_id"]` value that
the immediately preceding `runs_dir_for` call (round 4, two lines above)
already validated — `runs_dir_for` charset-checks `loop_id` itself, not only
`unit_id` — so that specific call cannot raise on this path today. Wrapped
it anyway, for defense in depth and consistency with this module's own
established style, and documented in-line why no new test covers it (one
would only re-prove the existing round-4 coverage). `cmd_finalize`'s call is
the genuine gap: nothing in that function validates `state["loop_id"]`
first, so a corrupted state file crashed it uncaught. Fixed with the same
`try`/`except ValueError` shape, returning a structured `{"error": ...}` on
stderr and exit 1 (mirroring `sub_iterate_finalize_summary`'s existing
error-return convention two branches above it in the same function). One new
regression test, in the same round-4 sibling file (still well under the
300-line guideline): `test_autonomous_loop_record_runs_dir_safety.py`.

## Consequences

- `_reconcile_in_progress` may grow further before the anti-ratchet blocks
  again (539-line current, per Round 5 growth above). Not a licence to keep
  growing — the next crossing needs its own ADR.
- `test_autonomous_loop_record_runs_dir_safety.py` is a brand-new file — no
  baseline implication, it never existed before this round.
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
