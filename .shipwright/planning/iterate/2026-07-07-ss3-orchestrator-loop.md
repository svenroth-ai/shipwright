# Iterate: SS3 — Single-session orchestrator loop + lifecycle integration + strict-stop

- **Run ID:** iterate-2026-07-07-ss3-orchestrator-loop
- **Campaign:** 2026-07-07-single-session-pipeline (sub-iterate SS3)
- **Intent:** FEATURE (campaign) · **Complexity:** medium · **Autonomy:** AUTONOMOUS
- **Spec Impact:** ADD (new `single_session` execution path; `multi_session` default untouched)

## Problem / Decision trace (Karpathy §1)

`multi_session` advances each phase from its own external `claude --session-id`
session (a phase Stop hook plans the next), so surfaces that can't launch a bound
session (VS Code extension, desktop chat) stall at phase 1. SS1 landed the
`mode` flag + contracts; SS2 the gate policy. SS3 must wire the **loop** that
drives every phase from ONE master conversation.

**Alternative considered:** put the loop in the `single_session/` package next to
`loop_state`/`result_contract`. **Rejected** — the SS1 lifecycle-reuse contract
test (`test_single_session_lifecycle_reuse`) ast-forbids that package from calling
a phase-task mutator. The loop's whole job is to call them, so it lives in
`orchestrator_pkg/` (where `router.py` already calls the lifecycle), importing the
pure `single_session` data contracts.

**Decision:** two orchestrator subcommands (`single-session-next` /
`single-session-apply`) the master alternates with a phase-runner subagent, both
reusing `phase_task_lifecycle` (claim / freeze_splits / complete / mark_failed) —
no bespoke completion path, no direct run_config mutation. Serial splits only in
v1. Design completion freezes splits BEFORE completion (mirrors
`phase_session_stop`) so build fans out per split.

## Scope of change

- `orchestrator_pkg/single_session_loop.py` (new) — resolve / begin / next / apply / advance.
- `orchestrator_pkg/single_session_cli.py` (new) — argparse adapter + exit-code map.
- `orchestrator_pkg/cli.py` — wire the two subcommands.
- `skills/run/SKILL.md` + `references/single-session-loop.md` (new) — master loop protocol.
- `docs/hooks-and-pipeline.md` — SS3 between-phase-action note.
- Tests: `tests/test_single_session_loop.py` (unit), `integration-tests/test_single_session_pipeline.py` (composition).

## Confidence Calibration
- **Boundaries touched:** run_config (READ-only here; all writes via
  `phase_task_lifecycle`), the resumable loop pointer
  `.shipwright/run_loop_state.json` (SS1 `loop_state`), the phase-runner RESULT
  CONTRACT (SS1 `result_contract`), the orchestrator CLI surface (2 new subcommands).
- **Empirical probes run:**
  - Drove the full pipeline project→deploy incl. 2-split build fan-out through the
    real CLI subprocess → run.status `complete`, loop `complete`, serial split
    order `plan/01→build/01→plan/02→build/02` preserved (integration test, PASS).
  - Forced `ok:false` at plan → run.status `failed`, NO build successor appended,
    loop `failed` (integration + unit, PASS).
  - Malformed result → `invalid_result`, task stays `in_progress`, run stays
    `in_progress` (never reaches the lifecycle) (unit, PASS).
  - Recover-bumped version → apply rejected `stale_version` (exit 2), loop pointer
    untouched (unit, PASS).
  - ast-scan of both loop modules → zero direct run_config writers (unit, PASS).
  - Multi-session integration test still green (7/7) — additive, no regression.
- **Test Completeness Ledger:**

  | Behavior (AC) | Disposition | Evidence |
  |---|---|---|
  | Full pipeline incl. build fan-out advances in one loop (AC1) | tested | `test_full_pipeline_with_split_fanout_completes` |
  | Forced failure strict-stops via mark_phase_failed, no successor (AC2) | tested | `test_failure_mid_pipeline_halts_with_no_successor`, `test_apply_failure_strict_stops_no_successor` |
  | Loop composes with lifecycle helpers (AC3) | tested | `integration-tests/test_single_session_pipeline.py` (real CLI subprocess) |
  | Serial split order preserved (AC4) | tested | order assertion in `test_full_pipeline_...` |
  | No direct run_config mutation (AC4) | tested | `test_loop_modules_never_call_a_direct_run_config_writer` (ast) |
  | resolve guards mode / no-config / terminal signals | tested | `test_resolve_*` |
  | next claims + records loop_state; idempotent re-dispatch | tested | `test_next_dispatch_claims_and_records_loop_state`, `test_next_dispatch_reclaim_is_idempotent` |
  | design completion freezes splits before planning | tested | `test_apply_design_freezes_splits_and_fans_out` |
  | invalid result never reaches lifecycle | tested | `test_apply_invalid_result_never_reaches_lifecycle` |
  | stale CAS token fail-closed, loop pointer untouched | tested | `test_apply_stale_version_fail_closed_leaves_loop_state` |
  | End-to-end UAT on a real idea (AC5) | untestable | `requires-manual-visual-judgment` — Sven UAT (NEEDS-YOU), tracked below |

  0 testable-but-untested behaviors. AC5 is a human-judgment acceptance step (real
  end-to-end pipeline on a real idea) that also depends on SS4's phase-runner
  subagent; recorded `untestable` with a closed-vocab reason, not "could-test-but-didn't".
- **Confidence-pattern check:** depth — the loop drives 9 dispatches (incl. 4
  split-phase tasks) through the real CLI to a terminal run, plus each failure/CAS
  branch. Breadth — resolve guards, claim idempotency, freeze-before-plan,
  strict-stop, invalid-result, stale-CAS, and the ast no-writer guard. Integration
  composition — `test_single_session_pipeline.py` is the `category:"integration"`
  behavior proving the loop composes with the lifecycle helpers end-to-end.

## Follow-ups (NEEDS-YOU / next sub-iterates)
- **AC5 UAT (NEEDS-YOU):** run `/shipwright-run --mode single_session` on a small
  real idea end-to-end once SS4 lands the phase-runner subagent.
- SS4: phase-runner subagent + artifact persistence (fixes the section-writer bug).
- SS5: deeper resumability / recovery / observability on the loop pointer.
- guide.md: user-facing single_session docs deferred to the SS7 capstone (SS1/SS2
  precedent — the mode is not user-complete until the phase-runner + resumability land).
