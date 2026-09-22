# Bloat exception — `plugins/shipwright-iterate/agents/sub-iterate-runner.md` raised to 512-LOC

<!-- Named by run_id per `_template-bloat-exception.md` — this heading does
     NOT claim a numeric ADR-NNN; that identity is assigned later, at
     release, by decision_log.md. `shipwright_bloat_baseline.json`'s entry
     for this file is set to `"state": "exception", "adr": "ADR-pending:
     .shipwright/planning/adr/iterate-2026-09-22-r2-worktree-capability-bloat-exception.md"`. -->

- **Status:** accepted
- **Date:** 2026-09-22
- **Re-Review-Date:** 2026-12-22
- **Incident Reference:** `iterate-2026-09-22-r2-worktree-capability`
  (campaign-dag-scheduler R2). The limit was crossed adding the two new
  `campaign_worktree`/`state_path` Input parameters and the "Step-boundary
  liveness touches" section (the campaign session-lock + per-unit lease
  heartbeat wiring — R2's own scope explicitly requires this wiring to be
  LIVE, not deferred, unlike the worktree-checkout flip itself).

## Context

`sub-iterate-runner.md` is the runtime prompt for the subagent a campaign
spawns per sub-iterate — the same file ADR-119 already raised from 400 to
497 lines for the same reason (a mandatory step's *existence* must be in the
guaranteed-loaded prompt, not behind a pointer). ADR-119's own Consequences
section anticipated this: "The runner prompt may grow to 497 lines before
the anti-ratchet blocks. It is not a licence to keep growing: the next
crossing needs its own ADR." This is that next crossing.

R2 gives the campaign session lock and this unit's own lease a heartbeat at
three step boundaries (Step 1, before Step 4, before Step 5) so the runner
Task itself — the process actually occupying the shared worktree for the
whole of the loop's longest unbounded window — is no longer silently
unmonitored (`references/campaign-worktree.md`'s "touch coverage gap"
section). The two new Input parameters plus the trigger condition, the
step-boundary list, the actual bash commands, and the warn-and-continue rule
cost **+15 lines** (497 -> 512), after compressing the first draft (which
cost +30) by moving all rationale — why `--worktree "{project_root}"` and not
`{campaign_worktree}`, the session-id source, the touch-coverage accounting
— out to `references/campaign-worktree.md`, which already carries it in
full.

## Ousterhout Argument

Unchanged from ADR-119: the module is deep (five/seven input parameters in,
one `result.json` out; the whole autonomous iterate lifecycle behind that
narrow interface). The same reasoning that kept the F0.5/F2/F3a/F5 phase
list inline applies here — a subagent's system prompt is the only text
guaranteed to be loaded, so *that a step exists and must run* belongs in the
prompt; only *how exactly* (the full rationale for the field choice, the
coverage-gap accounting) may be delegated to `references/campaign-worktree.md`,
and this diff already delegates everything delegable.

## YAGNI Check

- The two new Input parameters are load-bearing today: without them, per the
  external code review finding this campaign's own history already hit,
  `campaign-mode.md`'s spawn brief would omit both and the touches below
  would never fire for any real campaign run.
- The step-boundary touch list and commands are load-bearing today: R2's
  spec scopes the lease-touch wiring itself as LIVE for this sub-iterate,
  not deferred to R4/R5a.
- The warn-and-continue sentence is load-bearing: without it, a future edit
  could plausibly make a heartbeat hiccup fatal to an otherwise-healthy
  build, which is the opposite of this mechanism's purpose.

Nothing here is speculative scope; nothing was removed before writing this
exception because nothing here failed the "needed today" test.

## Chesterton-Fence Check

The current shape (a short in-prompt trigger + command block, full rationale
delegated to `references/campaign-worktree.md`) mirrors ADR-119's own
division between "what must happen" (in-prompt) and "how exactly / why"
(reference doc) — not an accidental shape. The `## Bloat Checklist` section
remains untouched and out of scope here, same fence as ADR-119 recorded.

## Decision

Raise `current` for `plugins/shipwright-iterate/agents/sub-iterate-runner.md`
from **497 to 512**, `state: "exception"`, `adr: "ADR-pending:
.shipwright/planning/adr/iterate-2026-09-22-r2-worktree-capability-bloat-exception.md"`,
in the same commit as the change that crosses it. `RUNNER_DOC_LINE_CEILING`
in `plugins/shipwright-iterate/tests/test_sub_iterate_runner_step_3_4.py`
moves to 512 in the same diff.

**Retirement plan.** Same as ADR-119's: retired by removing the duplication
between this file and its references, not by trimming further prose — a
loader able to inline shared prose into an agent prompt at spawn time would
let both the finalization-phase list and this section collapse to a
generated block. That premise remains unbuilt at this writing; the
2026-12-22 re-review should check whether it exists.

## Consequences

- The runner prompt may grow to 512 lines before the anti-ratchet blocks
  again. Not a licence to keep growing — the next crossing needs its own ADR.
- `shared/tests/test_r2_worktree_capability_prose.py` now pins the two new
  Input parameters and the `--worktree "{project_root}"` /
  `--campaign-worktree "{campaign_worktree}"` field split in the command
  block, so a future edit that drops either is caught immediately.
- `references/campaign-worktree.md`'s "Per-unit worktree path" section is now
  the SOLE place carrying the field-choice rationale — a reader who only
  loads `sub-iterate-runner.md` sees the rule but not the "why"; acceptable
  per the Ousterhout argument above (existence vs. rationale split).

## Rejected alternatives

- **Leave it at 497 and defer the wiring to R4/R5a.** Rejected: R2's own
  spec explicitly scopes the lease-touch wiring as in-scope now (only the
  worktree-checkout flip is deferred); deferring the wiring too would leave
  the campaign session lock's own "touch coverage gap" open for another two
  sub-iterates' worth of campaigns.
- **Shallow refactor — compress further.** Attempted: the first draft cost
  +30 lines with full inline rationale; compressing to a bare trigger +
  command block plus a single mirror-pointer recovered half of that (+15).
  Compressing further would drop the actual `--worktree`/`--campaign-worktree`
  distinction or the warn-and-continue rule from the guaranteed-loaded
  prompt — exactly the failure mode ADR-119 named.
- **Extract the whole section to `references/campaign-worktree.md` with only
  a one-line pointer left in-prompt.** Rejected on the same Ousterhout
  ground as ADR-119: the *existence* of a mandatory step must be
  guaranteed-loaded, not best-effort; a bare pointer risks the touches never
  running because the agent never followed it.
