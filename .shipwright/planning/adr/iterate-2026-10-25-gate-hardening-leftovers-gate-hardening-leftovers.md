# Driven-run gate leftovers: cap held in code, archived splits judged, one version default

Run: `iterate-2026-10-25-gate-hardening-leftovers` · spec:
`.shipwright/planning/iterate/iterate-2026-10-25-gate-hardening-leftovers.md`.
Leftovers of campaign `brief-driven-run-a-real-gates` (A3, A4, A5 and the two follow-up
iterates). Each item was located on `origin/main` (5b6686ae5) and decided with evidence.

## Decisions per item

1. **A3 accepted lows — fixed.** `_validate_plan`'s docstring claimed the split membership
   check keeps a plan from naming a path outside `.shipwright/planning/`; it only runs when
   the run's splits resolve (PR #904 Tier-3 review). Reworded. The A3 records name no single
   misnamed test; `test_skip_reason_accepts_only_non_blank_strings` was chosen by inspection
   because it never passed a blank string — it now does (both keys, whitespace, fall-through).
2. **A4 notes.**
   - (a) **Fixed.** The override refusal is recognised by type: `completion_hook` catches
     `phase_gate.OverrideRefused`, appends it to a `refusals` list and re-raises; apply maps
     `on_complete_failed` to `override_requires_human` only when that list is non-empty. No
     import cycle (completion_hook already imported phase_gate).
   - (b) **Pinned.** Order is gate, then split-authority read (outside the lock), then
     `freeze_splits` in the completion's locked write. A rejected design apply (retry due or
     `ask_human` terminal) leaves the run config byte-identical. Known limit: the gate and the
     freeze read the split authority separately.
   - (c) **Fixed in code.** An `ask_human` terminal writes `gateTerminal = {phaseTaskId,
     version, issues}` to `run_loop_state.json`. The read-only resolver answers
     `{action: "ask_human", reason: "phase_gate_terminal", ...}` (exit 0, nothing claimed)
     while it matches the frontier's run, id and version. Stale by construction: recover bumps
     the version; a completion moves the frontier. Deriving it from `attempt` /
     `gateRejections` was rejected (plan review): those cannot tell a crash-resumed dispatch
     from a capped one and miss early non-retryable terminals and unknown autonomy.
   - (d) **Documented only.** Nothing proves a person made a v2 override: anyone who can run
     `single-session-apply` can pass `--override-reason`; the record names reason, autonomy
     and entrypoint, not who typed it.
3. **Archived split — fixed.** For a non-final split `archive_split` runs before apply
   (`sections` = `[]`). The enforced gate asked "No sections found for current split" and the
   canon per-section checks passed vacuously. Validator and canon now read the task's split
   via `sections_for_split` (run plugin) mirrored by `shared/scripts/tools/verifiers/
   build_split.py` (import-free, pinned equal). Asks on an archived split carry `kind:
   archived_split` (non-retryable: a re-dispatch builds the next split). An installed
   `run_build_checks` without `split_id` is an ask-level `canon_degraded` note (version-skew
   shim, removable once every cache carries the new verifier).
4. **FR tags — fixed.** The three A3 validator test modules move from `FR-01.01/AC01`
   (pipeline order) to `FR-01.01/AC02` (a phase that failed its checks is not finished).
5. **Version default — fixed.** `phase_task_core.DEFAULT_TASK_VERSION = 1` + `task_version()`
   used by the owner check (was 0), dispatch descriptor, apply CAS and both recover paths.
6. **Raw `claim-phase-task` rotation — documented only.** Only `single-session-next`
   dispatches and it rotates through `redispatch_phase_task`; rotating inside the claim would
   double-bump there and break the documented idempotent same-session re-claim. No production
   caller re-claims raw (CLI and tests only), and a raw `ok:true` completion is refused while
   enforcement is on. Consequence: the cap is enforced at the loop's dispatch command; a raw
   claim is not refused.

## Reviews

Internal plan review (opus): medium, 10 fixed, 1 disclosed — the design moved from counters
to the persisted marker. Internal architecture review (opus): approve. External plan review:
glm approve, openai revise (stale mini-plan, skew guard, per-split history) — all fixed.
External architecture review: glm approve, openai approve.
Cascade (opus): spec PASS; code approve (7 low, 4 fixed incl. a real two-split
`archive_split` CLI integration test); doubt (2 medium, 2 low, all fixed: `recover_useful`
false for an archived split, uncounted `ask_human` terminals also write the marker, canon
gets `split_id` only for an archived split, the archived bucket needs the exact name in
`completed_splits`). External code review: glm approve, openai revise (an archived split's
`canon_degraded` ask lost its archived context; fixed with an `archived_split: true` flag).

## Not covered (follow-ups)

- Plan canon checks get no `split_id`.
- v1 `update-step --step build` after `archive_split` passes no split.
- `shared/scripts/lib/phase_invocation_mode.py` reads `task.get("version")` raw.
- The WebUI may not render the `ask_human` next action.
