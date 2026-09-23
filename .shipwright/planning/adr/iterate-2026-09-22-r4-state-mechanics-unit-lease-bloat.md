# Bloat exception — `shared/scripts/lib/unit_lease.py` raised to 323-LOC

<!-- Named by run_id per `_template-bloat-exception.md` — this heading does
     NOT claim a numeric ADR-NNN; that identity is assigned later, at
     release, by decision_log.md. `shipwright_bloat_baseline.json`'s entry
     for this file is set to `"state": "exception", "adr": "ADR-pending:
     .shipwright/planning/adr/iterate-2026-09-22-r4-state-mechanics-unit-lease-bloat.md"`. -->

- **Status:** accepted
- **Date:** 2026-09-23
- **Re-Review-Date:** 2026-12-23
- **Incident Reference:** `iterate-2026-09-22-r4-state-mechanics` (campaign
  `campaign-dag-scheduler`, sub-iterate R4), PR #790 round 22. External
  Tier-3 review (GPT) found `touch_unit_lease` validated a SUPPLIED
  `attempt_id` against the row's current value (rounds 7-8, an earlier
  R4 pass) but never required one when the row already carried a real
  token — a caller that simply omitted `--attempt-id` could still mutate
  a claimed row's lease fields, including extending `lease_expires_at`
  indefinitely, with no proof of current ownership. That gap crossed the
  300-line limit closing it.

## Context

`unit_lease.py` is R2's per-unit lease/heartbeat mechanism — see its own
module docstring for the full "why a field-creating upsert, why no
fencing at first" history. R4 (this sub-iterate, PRE-existing to this
round) already added the round 7-8 partial fencing: a SUPPLIED
`attempt_id` is validated against the row's real token. Round 22 closes
the remaining half of that same responsibility — REQUIRING a token when
one exists, not merely validating one if supplied — inside the same
function, the same already-counted responsibility (rounds 7-8's own
fencing check), not a new one.

## Ousterhout Argument

`unit_lease.py` is a single deep module around one narrow interface —
`touch_unit_lease(state_path, unit_id, ...)` — hiding a genuinely
substantial implementation: file-locking, atomic write, the
field-creating-upsert vs. never-mint distinction between lease fields and
`attempt_id`, the ghost-touch/`stale_attempt_conflict` diagnostic, and now
the ownership-proof requirement this round adds. Every one of these exists
to answer the same single question a caller asks once — "is my heartbeat
for this unit still valid, and did it get recorded?" — and none of them
is independently reusable or independently testable in a way that would
benefit from a second file. Splitting the fencing check (rounds 7-8 +
this round) into its own module would separate it from the exact row
lookup (`_find_unit`) and lock (`_lock_path`) it depends on, buying no
encapsulation — the same shape the sibling `loop_state.py`/`loop_claim.py`
bloat ADRs already reject for the same reason.

## YAGNI Check

- The lease fields (`lease_touched_at`, `lease_expires_at`, `worktree`,
  `branch`): needed today — `check_unit_lease.py`'s only production
  caller, `sub-iterate-runner.md`'s step-boundary touches, already wired
  since R2.
- `attempt_id` validate-if-supplied (rounds 7-8): needed today — the
  fencing primitive this same campaign's `loop_claim.py`/`loop_state.py`
  rely on for every OTHER claim mutation; leaving this one call site
  unfenced while every other mutator is fenced was the exact inconsistency
  round 22 flagged.
- `attempt_id` require-if-existing (round 22, this exception): needed
  today, even though it is a no-op against every row currently in
  production — see "Known limitation" in the module's own docstring:
  `loop_claim._claim_unit` (via `cmd_next_batch`) is the sole minter, and
  nothing dispatches through that path until R5a's flip
  (`campaign-mode.md`'s own "R4's cmd_next_batch is the first wiring
  point" note). The check is needed NOW, in this diff, because it is the
  correctness guarantee R5a's future wiring will rely on being already
  true — adding it reactively after R5a starts minting real tokens would
  mean shipping the exact vulnerability window round 22 describes, for
  however long the gap between "R5a mints tokens" and "someone notices
  lease touches still don't require them" lasts.
- **Explicitly NOT done, YAGNI on the other side:** wiring
  `sub-iterate-runner.md`'s heartbeat calls to actually PASS
  `--attempt-id` is deliberately left undone — that is R5a's own explicit,
  already-documented deferral (doubt-reviewer, medium, cited verbatim in
  this module's "Known limitation" section), not an oversight of this
  round. No current caller's row ever carries a real `attempt_id`, so
  this round's check is inert today and only takes effect once R5a's own
  wiring lands — building the runner-side wiring now, before R5a decides
  its actual dispatch shape (single-unit vs. batch-claimed, template
  parameters not yet designed), would be speculative engineering against
  a caller that does not exist yet.

## Chesterton-Fence Check

Round 7-8's fencing check (predating this round) already established the
"validate a supplied token, reject a mismatch, including a token-less row"
shape — its own comment explains the round-8 minting-gap fix. Round 22's
addition is not tearing down that fence; it is the missing complement the
fence's own docstring already flagged: rounds 7-8's own comment says "A
caller that supplies no token (every caller today) is unaffected either
way" — stated as a fact about TODAY's callers, not a claim that this is
the intended final shape. The module's own "Known limitation" section
(doubt-reviewer, predating this round) already named this exact gap and
explicitly deferred only the RUNNER-WIRING half to R5a — never the
validation half, which this round closes.

## Decision

Raise `current` for `shared/scripts/lib/unit_lease.py` from (untracked,
under 300) to **323**, `state: "exception"`, `adr: "ADR-pending:
.shipwright/planning/adr/iterate-2026-09-22-r4-state-mechanics-unit-lease-bloat.md"`,
in the same commit as this fix. **Retirement plan:** re-review at
2026-12-23 whether R5a's actual runner-wiring work (once its dispatch
shape is designed) reveals this module should split along the boundary
between "lease upsert" and "ownership-proof fencing" — a real question
only once R5a's caller shape exists to design the boundary around, not
before.

## Consequences

- The next campaign-dag-scheduler sub-iterate (R5a) that wires
  `--attempt-id` through the runner's heartbeat calls operates against the
  current 323-line ceiling, not the old under-300 baseline — a further
  crossing needs its own ADR (or this one's `current` bumped, if R5a's own
  work stays inside this file).
- No test file needed its own bump: the new regression coverage lives in
  the sibling `shared/tests/test_unit_lease.py`, which was already tracking
  this module's fencing behavior from rounds 7-8.
- `campaign-worktree.md`'s "No fencing-token validation applies to it"
  prose (R2-era) is now stale for the specific "tokenless touch of an
  already-claimed row" case — it still correctly describes today's
  production behavior (no row carries a real token yet) but should be
  revisited once R5a's wiring lands, alongside that same doc's own
  "Known limitation" pointer.

## Rejected alternatives

- **Split `unit_lease.py` into an upsert module and a fencing-check
  module.** Rejected — see Ousterhout Argument above: both halves share
  the same row lookup, lock, and single public entry point; splitting
  would only move the file boundary, not remove a dependency.
- **Defer round 22's whole finding to R5a, matching the runner-wiring
  half.** Rejected — the validation half (require a token when one
  exists) is safe, real, and a no-op against every row in production
  today; deferring it would mean R5a's own future wiring work lands
  against an UNFENCED `touch_unit_lease`, reintroducing the exact window
  round 22 flagged for however long it takes R5a to notice and fix it
  itself. Closing it now, while it costs nothing, is strictly better than
  leaving a known gap for a future sub-iterate to rediscover.
- **File no exception; let the post-merge Group H detective audit surface
  it.** Rejected — the crossing is certain and immediate (323 vs. limit
  300), not a maybe; filing now, in the same diff, is the documented
  anti-ratchet-compliant path this whole campaign has followed for every
  prior crossing.
