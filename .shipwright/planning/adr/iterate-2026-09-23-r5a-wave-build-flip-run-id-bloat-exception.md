# Bloat exception — `shared/scripts/lib/phase_quality/_run_id.py` raised to 335-LOC

<!-- Named by run_id per `_template-bloat-exception.md`; `shipwright_bloat_baseline.json`
     gains a NEW entry for this file (none existed before this sub-iterate),
     `"state": "exception", "adr": "ADR-pending:
     .shipwright/planning/adr/iterate-2026-09-23-r5a-wave-build-flip-run-id-bloat-exception.md"`. -->

- **Status:** accepted
- **Date:** 2026-09-23
- **Re-Review-Date:** 2026-12-23
- **Incident Reference:** `iterate-2026-09-23-r5a-wave-build-flip` — external
  code review (round 2, both `glm` and `openai`) found a real correctness gap
  in this sub-iterate's own first fix: the sentinel's tier-3 fallback
  (`resolve_wave_safe_unit_value` -> `""`) still risked colliding sibling
  units in a wave, because `resolve_run_id`'s OWN tier 1 (`pointer_run_id`)
  is keyed by `session_id`, and every unit in a wave shares the same
  `SHIPWRIGHT_SESSION_ID` — N concurrent `setup_unit_worktree.py` calls all
  write to the same `<main_root>/.shipwright/iterate_active/<session_id>.json`,
  last-writer-wins.

## Context

Held at exactly 300 lines earlier in this same sub-iterate (per its own
docstring, split out of `_resolution.py` at the 300-LOC ceiling). The fix for
the round-2 finding — resolving the wave-sentinel case through
`lib.campaign_wave.per_unit_worktree_identity` (the worktree's OWN directory
basename, safe under concurrency and requiring no change to session/lock/lease
semantics elsewhere) BEFORE giving up to `loop_id` alone — could not be
compressed back to 300 without cutting either the new import or the existing,
already-reviewed docstring/comment trail this file carries from three prior
external-review rounds (trg-b36fd844 among them). Cutting inherited review
history to make room for a NEW fix is the wrong trade.

## Ousterhout Argument

This function's whole reason to exist (per its own docstring) is a single
composite-fallback resolution ladder that must be read as one ordered
sequence — splitting the wave-sentinel branch out to a second file would put
one rung of the SAME ladder somewhere else, which is a worse interface than a
5-line growth.

## YAGNI Check

The added lines are the fix itself (a new import + a 3-line branch); nothing
speculative was added alongside it.

## Chesterton-Fence Check

Every existing comment kept in place documents a specific prior review
finding (trg-b36fd844, ADR-045, the `isinstance(data, dict)` guard) — none of
those fences were touched.

## Decision

Add a NEW baseline entry for
`shared/scripts/lib/phase_quality/_run_id.py`: `limit: 300`, `current: 335`,
`state: "exception"`, `adr` pointing to this file.

## Consequences

- `_run_id.py` may grow up to 335 lines before the anti-ratchet blocks again.
- No test currently pins this file's line count; none is added — the
  anti-ratchet hook itself reads the baseline directly.

## Round 3 growth (305 -> 335)

Code review round 3 (opus, internal) found a second, more severe instance of
the same class of bug: `resolve_run_id` tries `pointer_run_id` at **tier 0**,
*before* it ever reaches tier 3's wave-safe `per_unit_worktree_identity`
fallback (the round-2 fix above). `pointer_run_id` and `pointer_worktree_root`
both read the same session-keyed pointer file, so the identical
last-writer-wins collision that motivated the round-2 fix was still reachable
one tier earlier — every unit in a wave could silently resolve to whichever
sibling's pointer was written last, for the entire run.

Fixed by adding one helper, `_pointer_targets_a_different_wave_unit(pointer_worktree,
caller_root)`, called from both `pointer_run_id` and `pointer_worktree_root`
right after their existing liveness/worktree-membership checks. It is gated on
`per_unit_worktree_identity(caller_root) is not None`, so it is inert for a
standalone iterate or a main-root call (`audit_phase_quality_on_stop.py`), and
is INTENDED to activate when the caller is itself a per-unit wave worktree
(`mark_implementation_span.py`'s call shape, `cwd = Path.cwd()`) — **whether
`Path.cwd()` genuinely resolves to the per-unit worktree inside that hook's
own subprocess during a real wave is not yet verified; see "Round 4 code
review" below.**

Splitting this helper into a separate file was rejected for the same
Ousterhout reason as the round-2 growth: it is one more rung on the same
composite-fallback ladder both pointer functions already implement in this
file, and putting it elsewhere would separate two checks that must be read
together to see why either exists.

## Round 4 code review — HIGH finding: investigated, correction, still OPEN

Round 4 (internal, opus re-review) raised a HIGH doubt: does
`per_unit_worktree_identity(Path.cwd())` — the gate both round-3 fixes and
`write_wave_aware_handoff` depend on — actually see the per-unit worktree
inside a `sub-iterate-runner` subagent's own hook subprocesses (Stop,
PostToolUse) during a real wave, or does it see the shared campaign
worktree/main instead, making the fix inert in production despite passing
its own unit tests (which pass the worktree path directly, never through a
real hook invocation)? The reviewer explicitly asked for "one real probe,
not reasoning."

**This section originally closed the doubt as "verified to activate as
designed." Round 5 re-review checked that reasoning against the sources it
cited and found it did not hold, and that the codebase's own evidence points
the other way:**

- The cited `docs/hooks-and-pipeline.md` "Monorepo Auto-Descent Guard" quote
  ("`cd <managed-subdir>` — cwd is then `project_root`...") sits under
  "Opt-in for cross-dir audit (e.g. CI/automation)" and states which cwd a
  hook fires FROM in that framing — it never claims a `cd` an agent's own
  Bash tool issues mid-session propagates into a LATER harness-spawned hook
  subprocess. Its own sibling bullets (`SHIPWRIGHT_PROJECT_ROOT`, the
  pointer-verified redirect) are exactly the mechanisms that WOULD be needed
  if it did not.
- The R1-R4 "already worked in production" argument is non-discriminating:
  at N=1, tier 0 resolves correctly whether the hook's cwd is the per-unit
  worktree OR main, since the one session-keyed pointer names the only live
  unit either way — and `_pointer_targets_a_different_wave_unit` did not
  exist in R1-R4, so no cwd-shape-dependent branch was ever exercised by
  those runs.
- The claim that "the standalone flow never issues a bare `cd`" is FALSE:
  `references/F11.md`'s own PR-creation step does `cd "{project_root}"`,
  with the comment "so `gh` can never operate on the main repo **even if the
  shell cwd drifted**" — the codebase's own prose treats shell cwd as
  unreliable, the opposite of what this section concluded.
  `references/campaign-worktree.md` does a bare `cd` too. And
  `_worktree_identity.py`'s `fast_main_root` docstring calls
  `cwd == main repo root` **"the dominant shape"** for a Stop subprocess and
  justifies a MEASURED 30-80ms fast path on that basis — direct, empirical,
  in-repo evidence pointing away from this section's conclusion.

**Current status: genuinely unverified, not fixed, not disproven.** If the
gate is in fact inert in the real hook shapes (`mark_implementation_span.py`,
`generate_handoff_on_stop.py`), `per_unit_worktree_identity(Path.cwd())`
returns `None`, `_pointer_targets_a_different_wave_unit` short-circuits
`False`, and tier 0 hands every unit in a wave whichever sibling's setup call
wrote the shared session-keyed pointer last — the exact round-3 collision,
live, for the run_id these hooks attribute audit findings, triage cards, and
handoff namespacing to. No code change was made against this uncertainty
(a robust fix that does not depend on hook-subprocess cwd resolution at all
is more than this sub-iterate's own scope should absorb reactively) — the
concrete, cheap follow-up (round 5's own suggestion): the FIRST time a real
multi-unit wave runs (`WAVE_MAX_PARALLEL` > 1 in production), have a
runner's Step 1.0 emit `pwd` as its first post-`cd` Bash call, and/or one
Stop hook log `Path.cwd()` once under the wave sentinel, so the very first
live wave settles this empirically instead of continuing to reason about it.
Whoever drives that first live wave (this campaign's own remaining
sub-iterates, or a later campaign) should treat this section as the trigger
to run that check before trusting per-unit run_id attribution during a wave.
The genuinely real, ALREADY-documented residual for the case where the
guard's precondition (`per_unit_worktree_identity(caller_root) is not None`)
correctly fails to hold — a caller rooted at main or the shared campaign
worktree during a live wave — is unaffected by this correction and remains
in `docs/hooks-and-pipeline.md`'s R5a exception paragraph.

## Round 6 doubt review — six doubts, independently verified, dispositioned

A fresh-context adversarial doubt review over the full R5a diff (merge-base
`ba65b33b4842dc5049429a6fdc14cf6d90e5daa3` to `80932c70a`) raised six doubts.
Per this campaign's own discipline (never trust a reviewer's finding without
independently reading the actual cited code first), each was checked against
the real files before any fix. Findings:

1. **HIGH — CONFIRMED AND FIXED.** `setup_unit_worktree.py`'s `main()`
   computed `main_root = main_repo_root(project_root)` at line 76 (for the
   Windows path-length check only) but then called
   `setup_iterate_worktree(str(project_root), ...)` — the RAW,
   possibly-a-linked-worktree path, not `main_root`. Independently confirmed
   by reading `setup_iterate_worktree.setup()`'s first branch
   (`is_worktree(root): ... return 0, {"action": "noop", ...}`, no worktree
   ever created) and `git_base.is_worktree()` (`git_dir != common` — true
   for ANY linked worktree, including the shared campaign worktree itself,
   which campaign-mode.md's own line 148 already documents as
   `{project_root}` for 3c's call). Since campaign-mode.md 3c invokes this
   wrapper with `--project-root "{project_root}"` = the shared campaign
   worktree, every wave would have hit the no-op branch, never created a
   per-unit worktree, then correctly failed the per-unit spawn-guard's
   basename check and STRICT-STOPped — the flip would not have built a
   single unit on its first live invocation. Confirmed no existing test
   exercised `--project-root` = a linked worktree (both
   `test_setup_unit_worktree.py` and `test_r2_worktree_capability_integration.py`
   only ever pass the main repo root). **Fix:** pass `main_root` (already
   computed) instead of `project_root` to `setup_iterate_worktree()` — one
   line. **Regression test added:**
   `test_project_root_as_a_linked_worktree_still_creates_a_real_per_unit_worktree`
   in `test_setup_unit_worktree.py` — creates a linked worktree, points
   `--project-root` at it, asserts `action == "created"` with the correct
   per-unit sibling path. Verified the test fails (`noop`, not `created`)
   against the pre-fix code and passes against the fix.
2. **Plausible, real risk class — DEFENSIVELY FIXED.** `WAVE_MAX_PARALLEL` is
   exported once at loop step 1 and consumed later at 3a via
   `"$WAVE_MAX_PARALLEL"`, but step 1 and 3a are separate numbered steps
   executed as separate Bash tool calls interleaved with `Task` spawns over
   the loop's life — shell-state persistence across that specific boundary
   (separate Bash invocations interleaved with `Task` spawns) is not
   guaranteed by anything this repo controls. An
   argparse-required-int arg reading empty is a structural error that exits
   2, indistinguishable from 3a's own "every unit TERMINAL, done" exit code
   — campaign-mode.md's own round-2 comment already named this exact risk
   shape but the round-2 fix (exporting the value at all) does not address
   the cross-call survival question. **Fix:** 3a's own invocation now reads
   `"${WAVE_MAX_PARALLEL:-4}"` — a lost export degrades to the documented
   constant instead of a silent false-"done". The broader design smell
   (`loop_claim.py` reusing exit 2 for both "done" and any argparse
   structural error) predates R5a — the single-unit `cmd_next` already did
   this — and is not this sub-iterate's to redesign.
3. **(a) CONFIRMED, not fixed here.** `generate_handoff_on_stop.py` is
   registered on the `Stop` key of every phase plugin's `hooks.json` (all
   eleven of them, including `shipwright-run`) and on no `SubagentStop` key
   anywhere in the repo — `SubagentStop` itself is used, just only by
   `shipwright-build` (`write-review-payload-on-stop.py`,
   `cleanup-review-scratch-on-code-reviewer-failure.py`) and
   `shipwright-plan` (`write-section-on-stop.py`), neither of which touches
   this hook. A `sub-iterate-runner` terminates via
   `SubagentStop` on the orchestrator's own session, so this hook only ever
   runs for the orchestrator itself, whose cwd is definitionally the shared
   campaign worktree. Its per-unit `write_wave_aware_handoff` branch is
   therefore unreachable during a live wave, independent of the Path.cwd()
   question in "Round 4" above — `session_handoff.md`'s attribution always
   takes `resolve_fallback()`. Not fixed: `session_handoff.md` is already
   documented (skill Step B1) as a secondary, best-effort convenience no
   gate reads authoritatively, so a wrong per-unit name in it is real but
   proportionate; a correct fix needs its own registration point and is its
   own follow-up, not a reactive patch bundled into this round.
   **(b) Same open question as "Round 4", not a separate confirmed bug.**
   `mark_implementation_span.py`'s resolved-pointer cache and done-marker are
   keyed off `repo_root_hint(cwd)`, which walks UP from cwd for the FIRST
   ancestor owning both `.git` and `.shipwright` — starting from a per-unit
   worktree (which itself has both), that IS the per-unit worktree, stopping
   immediately. If `Path.cwd()` genuinely resolves to the per-unit worktree
   inside this hook's own subprocess, this cache is already per-unit-isolated
   for free, by the same mechanism the tier-0/tier-3 fix depends on; it is
   the SAME unresolved premise, not an independently confirmable second bug.
   Added to the existing cheap first-live-wave probe's scope rather than
   given its own speculative fix.
4. **REFUTED.** Doubt: concurrent `git fetch`/`checkout -b` races across
   sibling worktrees sharing one `.git` object store, since a wave spawns
   multiple units at once. Independently checked campaign-mode.md 3c's own
   prose: "For EACH unit in `claimed` (fixed order), create its OWN per-unit
   worktree" — every `setup_unit_worktree.py` call for the whole wave runs
   sequentially, in the orchestrator's own fixed-order loop, strictly BEFORE
   the multi-`Task` spawn. No two `setup_unit_worktree.py` invocations for
   the same wave are ever concurrent; only the subsequent BUILD work is.
5. **Acknowledged, pre-existing-class gap — not fixed.** A wave that crashes
   mid-3c (after some per-unit worktrees/branches exist, before STRICT-STOP
   completes) leaves artifacts a retried wave's `setup_unit_worktree.py` call
   would hit as `worktree_exists`/`branch_exists` collisions, STRICT-STOPping
   the retry too. Real, but not a new failure class R5a introduces — the
   single-unit model had the identical worktree/branch-collision-on-retry
   shape for one unit at a time; R5a generalizes it to "possibly several
   units at once," it does not create it. The collision payload's own
   `detail` already names the manual remedy (`git worktree remove` / `git
   branch -D`). A dedicated stale-artifact sweep is a properly-scoped
   follow-up, not this round's to build reactively.
6. **Acknowledged, pre-existing-class gap — not fixed.** A session killed
   mid-wave after `Task` spawn but before 3e's reconciliation leaves rows
   `running` with no live owner, and `next-batch`'s stall report
   (`blocked_pending_ids`) does not surface a stuck `running` row (it reports
   blocked `pending` ones). Real, but the single-unit model already had this
   exact gap for its one `running` unit if killed at the equivalent point;
   R5a's concurrency means potentially several rows stuck this way instead
   of one, not a new class of gap. A liveness/staleness detector for
   `running` rows is a properly-scoped follow-up.

## Rejected alternatives

- **Trim the review-history comment trail to net back to 300.** Rejected —
  those comments are the record of three PRIOR external-review rounds fixing
  real bugs in this exact function; removing them to make room for a fourth
  finding's fix would make the NEXT reviewer re-discover the same ground.
