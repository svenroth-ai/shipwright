# A skip that clears the last open task completes a blocked driven run

Run: `iterate-2026-10-25-run-completion-after-skips` · BUG, small · FR-01.01 (AC01), requirement text unchanged (`spec_impact: none`, `restores-specified-behavior`).

## Context

`complete_phase_task` parks a driven run in `needs_validation` when the pipeline-terminal task completes while other `phase_tasks[]` are still open. The documented way out is `recover-phase-task --force-status skipped --reason "<why>"` per open task, but nothing re-checked the run afterwards: `recover_phase_task` never touched `run.status` for a skip, `single-session-next` answered `needs_validation` forever, and the run SKILL.md called it a known gap. The run could never finish.

## Decisions

1. **The skip re-checks the run-completion invariant in its own locked write.** `phase_task_recovery._completion_unblocked` lifts the pause only when all of these hold: `status == "needs_validation"`; no `validation_issues` key (the v1 producer `step_planning.update_step` always writes it, and a skip answers none of its findings); a task of the pipeline-terminal phase is `done`; every task is in `TERMINAL_STATUSES`. Then `config.status = "complete"` is written together with the skip (both or neither) and the result carries `run_status: "complete"`, which both recover CLIs print.
2. **The pipeline-terminal phase is `deploy`, or `changelog` when `deploy_target == "none"`.** These are exactly the two `None` successors of `phase_state_machine.next_phase_task`, i.e. the cases in which `complete_phase_task` applies the invariant; requiring only `deploy` would have left a deploy-less run with the same bug.
3. **A `--force-status failed` recover never completes the run by itself.** An operator who marks the last open task failed is declaring a failure, not finishing the pipeline; the run stays `needs_validation` (unchanged behaviour). An already-`failed` task does not block a later completing skip, exactly as in `complete_phase_task` (same `TERMINAL_STATUSES`); pinned by a test.
4. **The loop pointer follows.** `single_session_recovery.mark_loop_complete` stamps `.shipwright/run_loop_state.json` `complete` (only for an explicit `single_session` run, only for the same `runId`, only when run_config says `complete`; idempotent). It runs after every successful skip, not only the completing one, because the loop file is written outside the lifecycle lock: a loop write lost after the config write is repaired by the next skip. `single-session-next` decides from run_config alone, so it already answered `complete`, but the pointer would have kept the `stopped` status the deploy apply left, which the session handoff prints as "Loop status". Both `recover-phase-task` and `single-session-recover` call it; the in-loop `recovery` event also carries `runStatus`. The lifecycle module itself still never writes loop state.

## Consequences

- A `needs_validation` run whose open tasks are all skipped now finishes without any hand edit; skipped tasks stay `skipped`.
- Like `complete_phase_task`, the invariant counts a `failed` task as terminal: if an earlier task was already `failed` when the last open one is skipped, the run is completed. That mirrors the existing producer exactly and is recorded as a follow-up question, not changed here.
- A skip plans no successor, so skipping an open `plan/<split>` after deploy closes the run without that split's build; the skip is the operator's decision and is recorded (`skipReason`, `phase_skipped`).
- Rejected: re-checking in `resolve_next_dispatch` (it is read-only by contract) and a separate "finish-run" command (one more step the operator has to know about).

## Self-Review

1. Spec Compliance — pass: every required case has a test; the deploy-or-changelog reading mirrors the producer.
2. Error Handling — pass: one `_write_config` under `_PhaseTasksLock`; the loop stamp is runId- and status-guarded.
3. Security Basics — pass: no new input surface.
4. Test Quality — pass: 13 unit tests over the real lifecycle (7 fail on the unfixed code) and one subprocess CLI test over real gates.
5. Performance Basics — pass: one linear pass over `phase_tasks` inside a lock already held.
6. Naming & Structure — pass: lifecycle owns run_config, `orchestrator_pkg` owns loop state; all files under their caps.
7. Affected Boundaries — pass: run_config and run_loop_state.json round-trip through their real readers in the tests.
8. Test Hygiene Probe — pass: `scan_test_hygiene.py --diff` reports no findings.

## Reviews

Spec review (opus): PASS. Code review (opus): PASS with two lows and one info, all accepted and fixed (a `runStatus` field on the in-loop `recovery` event; the completion stamp moved out from under the "terminal recoveries leave the pointer" comment and documented; one exit in `recover_phase_task`).

Doubt review (opus), each answered:

| # | Severity | Doubt | Disposition |
|---|---|---|---|
| 1 | medium | the loop write after the locked config write can be lost, and the transition-only stamp never repairs it | accepted-and-fixed: the stamp runs after every successful skip and checks run_config itself; test `test_a_later_skip_repairs_a_loop_write_lost_after_completion` |
| 2 | medium | failed-then-skip completes the run although a task failed | rebutted: identical to `complete_phase_task`'s invariant (the brief asked to mirror it); claims reworded to "a failed recover never completes the run by itself"; pinned by `test_an_earlier_failed_task_counts_as_terminal_like_the_deploy_completion`; open as a follow-up for both producers |
| 3 | low | a malformed v1 pause with `validation_issues: []` would look like the lifecycle's | rebutted: `update_step` writes the key only with a non-empty ask list and pops it only when no issue is left, and it is inert inside a driven run (drivability guard), so that state has no producer |
| 4 | low | the router path stamps loop state without a mode check | accepted-and-fixed: `mark_loop_complete` requires `is_single_session(config)`; test `test_loop_stamp_refuses_a_config_that_is_not_a_single_session_run` |
| 5 | low | a skipped task's successors are never planned | accepted as operator intent; stated in the docstring and above |

External code review (glm + openai via the codex transport, full merge-base diff): both approve, no findings. Plan, internal plan and internal architecture review: not applicable at small complexity.

## External-Code-Review-Findings

| # | Reviewer | Severity | Finding | Disposition |
|---|---|---|---|---|
| — | glm, openai | — | no findings (both approve) | — |
