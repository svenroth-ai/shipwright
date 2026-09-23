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
standalone iterate or a main-root call (`audit_phase_quality_on_stop.py`) and
only activates when the caller is itself a per-unit wave worktree
(`mark_implementation_span.py`'s real call shape, `cwd = Path.cwd()`).

Splitting this helper into a separate file was rejected for the same
Ousterhout reason as the round-2 growth: it is one more rung on the same
composite-fallback ladder both pointer functions already implement in this
file, and putting it elsewhere would separate two checks that must be read
together to see why either exists.

## Rejected alternatives

- **Trim the review-history comment trail to net back to 300.** Rejected —
  those comments are the record of three PRIOR external-review rounds fixing
  real bugs in this exact function; removing them to make room for a fourth
  finding's fix would make the NEXT reviewer re-discover the same ground.
