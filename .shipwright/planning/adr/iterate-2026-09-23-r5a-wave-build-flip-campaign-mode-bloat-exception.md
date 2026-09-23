# Bloat exception — `plugins/shipwright-iterate/skills/iterate/references/campaign-mode.md` raised to 1050-LOC

<!-- Named by run_id per `_template-bloat-exception.md` — this heading does
     NOT claim a numeric ADR-NNN; that identity is assigned later, at
     release, by decision_log.md. `shipwright_bloat_baseline.json`'s entry
     for this file is set to `"state": "exception", "adr": "ADR-pending:
     .shipwright/planning/adr/iterate-2026-09-23-r5a-wave-build-flip-campaign-mode-bloat-exception.md"`. -->

- **Status:** accepted
- **Date:** 2026-09-23
- **Re-Review-Date:** 2026-12-23
- **Incident Reference:** `iterate-2026-09-23-r5a-wave-build-flip`
  (campaign-dag-scheduler R5a — "the flip: wave-based concurrent build").
  The limit was crossed replacing the loop's single-unit spawn model
  (3a-3f) with the wave model: `cmd_next_batch`-based ready-set
  computation, per-unit worktree checkout, multi-`Task` spawn in one
  message, full-wave-return reconciliation (launch-failure release,
  running-with-no-result demotion), and fixed-order handoff into the
  existing 3f-bis..3h drain — plus the wave-scoped `SHIPWRIGHT_LOOP_UNIT_ID`
  sentinel's security rationale, which previously lived only in the plan
  document and now must be guaranteed-loaded here too (the same
  existence-vs-rationale split ADR-119/R2's own bloat exceptions on this
  file and on `sub-iterate-runner.md` already established).

## Context

`campaign-mode.md` is the runtime reference for `/shipwright-iterate
--campaign --autonomous`'s entire orchestrator loop — the only text
guaranteed to be read by the session actually driving a campaign. It was
already an `exception` at 810/400 lines (R3's own crossing, review-diff-fix
robustness). R5a's own job — replacing the orchestrator's fundamental
build-one-unit-at-a-time model with build-a-whole-wave-concurrently — is a
structural rewrite of steps 1-3f, not an additive step; the growth
(810 -> 983, **+173 lines**) is concentrated in: the wave-serialization
rule and its explicit non-goal (cross-wave pipelining), the new 3a
(`next-batch` + its distinct exit codes 2/4/6/1/0), 3b (per-unit run_id
minting, no more per-runner env export), 3c (per-unit worktree checkout +
multi-spawn + the full security enumeration for the sentinel), 3d (the
now-implicit wave-return, replacing the DONE-marker wait), 3e (the two
new reconciliation branches: launch-failure release, running-with-no-result
demotion), 3f (record, now unit-scoped and STRICT-STOPping the whole wave
on any failure), the wrapping paragraph handing the wave to 3f-bis..3h
unit-at-a-time, and 3i's wave-vs-loop continuation split. 3f-bis/3g/3h's
own bodies are UNCHANGED (R5b's job) — none of this growth touches them.

## Ousterhout Argument

Unchanged from R3's own exception on this file: the orchestrator loop is a
genuinely deep module — the interface a reader needs (what fires, in what
order, on what exit code) is narrow, and the implementation underneath (a
concurrent, fenced, multi-process state machine with a documented security
boundary) is genuinely substantial. Splitting `campaign-mode.md` into
per-step files would scatter the ONE place a driving session reads before
acting, which is exactly the failure mode `references/campaign-worktree.md`
already exists to avoid for the worktree-setup half of this same loop —
this file's job is the loop itself, and a loop's steps must stay adjacent
and ordered for a reader (or a re-entering, resumed session) to follow.

## YAGNI Check

- The wave-serialization rule and its non-goal are load-bearing today: the
  spec's own acceptance criteria name a dedicated test proving wave N+1 is
  not spawned before wave N's merge lane clears — a reader (or session)
  without this rule stated in-loop could plausibly try to overlap them.
- The full sentinel security enumeration is load-bearing: it is what a
  future edit to `capture_session_id.py`/`_run_id.py`/the authorship guard
  must consult before touching `SHIPWRIGHT_LOOP_UNIT_ID`'s semantics again,
  and it is a genuine, previously-undocumented-in-this-file security
  control, not narration.
- The two new reconciliation branches (3e) are load-bearing: without them
  stated in-loop, a launched-but-crashed unit's row would sit `claimed` or
  `running` forever with no path back to `pending`/`failed`, silently
  hanging the campaign.
- Nothing was removed before writing this exception because nothing added
  failed the "needed for THIS wave-return to behave correctly" test — this
  is a from-scratch replacement of the single-unit steps it removed, not
  additive narration on top of them.

## Chesterton-Fence Check

The existing fence — 3f-bis through 3i staying UNCHANGED, invoked once per
unit rather than rewritten for the wave model — is deliberate and
documented, not an oversight: R5a's own sub-iterate spec scopes the
merge-lane's actual revision (review pinning, staleness cascade) to R5b,
which has not been built yet at this sub-iterate's build time. Tearing that
fence down here (rewriting 3f-bis..3h against an unbuilt R5b design) would
duplicate work R5b's own acceptance criteria already claim. The fence
therefore stands for a real, near-term reason and is preserved as-is,
merely wrapped in a new per-unit drain loop.

## Decision

Raise `current` for
`plugins/shipwright-iterate/skills/iterate/references/campaign-mode.md`
from **810 to 1050** (983 at initial write; +6 from external code review
round 1's two fixes — the attempt-scoped 3e read path and the explicit
exit-3 STRICT-STOP note on the synthetic no-result record; +10 from round 2
— the 3c launch-failure release-every-claimed-unit fix and 3i's no-progress
guard sentence; +12 from the orchestrator's own spec-compliance review —
exporting the real `WAVE_MAX_PARALLEL` shell variable at loop step 1 (it was
previously only declared in this file's own prose, so `--max-parallel
"$WAVE_MAX_PARALLEL"` at 3a expanded empty and would have exited 2 — read as
"done" — without ever claiming a unit), plus correcting two now-stale
references to the pre-flip terminal DONE-marker wait this file's own new 3d
text already retires; +31 from internal code review round 3 — correcting
the security note's stale claim that `_run_id.py`/handoff namespacing fall
back to the (rejected) session-keyed `resolve_run_id` pointer rather than
`per_unit_worktree_identity`; documenting `write_terminal_marker.py`'s new
no-op gate under the wave sentinel at 3d; and, at 3e, releasing any
remaining still-`claimed` units before a mid-reconcile STRICT-STOP, plus
surfacing an isolation-check failure's `reason_code` when its own
`result.json` exists — mirroring 3c's own release-before-STRICT-STOP fix
one reconcile step later; +4 from round 4's own re-review — 3c's release
branch excluded the failing unit itself, stranding exactly the claim whose
own failure triggered it; +4 from round 5's own re-review — retracting an
overclaim in the security note (and in the run-id bloat-exception ADR) that
the tier-0/tier-3 fix was "verified to activate" in production, since the
sources cited for that claim did not actually support it and the codebase's
own evidence points the other way; the doubt is now recorded as genuinely
open, with a cheap first-live-wave probe named as the way to settle it),
`state: "exception"`,
`adr: "ADR-pending:
.shipwright/planning/adr/iterate-2026-09-23-r5a-wave-build-flip-campaign-mode-bloat-exception.md"`,
in the same commit as the flip. `plugins/shipwright-iterate/tests/test_skill_references_link.py`'s
`_bloat_exception_budgets()` reads the baseline directly, so no separate
test-side ceiling constant needs updating.

**Retirement plan.** Re-review at 2026-12-23 whether R5b's own merge-lane
revision (landing on top of this file) can absorb some of 3f-bis..3h's own
prose into a shared reference doc the way `references/campaign-worktree.md`
already does for worktree setup — that would shrink this file's OWN line
count even as R5b adds its own new steps, rather than only ever growing it
further.

## Consequences

- The loop reference may grow further before the anti-ratchet blocks again
  (1050-line current). Not a licence to keep growing — R5b's own crossing,
  if any, needs its own ADR, following this same pattern.
- `shared/tests/test_r2_worktree_capability_prose.py`'s `_step_3c()` helper
  now anchors on the NEW 3c/3d labels this flip introduced
  (`"3c. **Per-unit worktree, then multi-spawn"` / `"3d. **Wave-return"`)
  — updated in the same commit.
- `shared/tests/test_campaign_wave.py`,
  `shared/tests/test_wave_launch_failure_and_reconcile.py`, and
  `shared/tests/test_derived_snapshots_wave_concurrency.py` are brand-new
  files exercising the state-machine primitives this prose now describes
  (`loop_claim.cmd_next_batch`/`cmd_release`, `loop_mark.cmd_mark_running`,
  `autonomous_loop.cmd_record`, `restore_derived_to_head`) — no baseline
  implication, none existed before this sub-iterate.
- `references/campaign-mode.md`'s own "Why interleaved-serial" section now
  documents an explicit, deliberate gap (intra-wave staleness) that R5b
  alone closes — a reader relying on the pre-R5a "no regenerate-at-merge"
  guarantee holding WITHIN a wave, not just across waves, would be
  incorrect until R5b lands.

## Rejected alternatives

- **Extract the wave-model steps to a NEW reference file
  (`campaign-wave.md`), leaving only a pointer in `campaign-mode.md`.**
  Rejected on the same Ousterhout ground R3's own exception already used:
  the loop's steps must stay adjacent and in order for a driving session to
  follow linearly; a cross-file jump mid-loop risks a resumed session
  reading half the steps from one file and half from a stale copy of the
  other.
- **Defer the wave-flip's security enumeration to a reference doc with only
  a one-line pointer in-prompt.** Rejected: the sentinel's security
  guarantee (the CI-supply-chain authorship guard's refusal) must be
  guaranteed-loaded by the session that exports it, not best-effort — the
  same reasoning ADR-119 already established for `sub-iterate-runner.md`'s
  own mandatory-step existence vs. rationale split.
- **Shrink 3f-bis..3h's own prose in the same diff to make room.**
  Rejected: those steps are explicitly R5b's to revise (Chesterton-Fence
  Check above); trimming them now for bloat-budget reasons alone, ahead of
  R5b's own design, risks silently dropping a control an earlier review
  round fought hard to establish (this file's own step 3f-bis prose
  documents at least three prior rounds of exactly that class of
  regression).
