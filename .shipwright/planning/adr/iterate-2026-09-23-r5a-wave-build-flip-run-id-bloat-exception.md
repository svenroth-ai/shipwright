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

## Rejected alternatives

- **Trim the review-history comment trail to net back to 300.** Rejected —
  those comments are the record of three PRIOR external-review rounds fixing
  real bugs in this exact function; removing them to make room for a fourth
  finding's fix would make the NEXT reviewer re-discover the same ground.
