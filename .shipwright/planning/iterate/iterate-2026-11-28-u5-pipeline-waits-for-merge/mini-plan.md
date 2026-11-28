# Mini-plan: U5 — Pipeline: a phase can wait for the release PR merge (shipwright-run)

Run: iterate-2026-11-28-u5-pipeline-waits-for-merge · Complexity: medium · Campaign dfp-changelog-followups

## Goal
A phase-runner result can say "this phase is not done, it waits for an outside event" (`waiting_for_merge`, with
the PR URL). The single-session loop then answers a `waiting` action: nothing is completed, nothing failed, no
successor is planned (deploy not scheduled), the run is not complete. The resume card says what to do. On resume the
same task is dispatched again; a later `ok` result moves on as today (deploy, or the run ends with `deploy_target:
none`). Inert until U6 makes the changelog phase emit it. No new value in `run_config.v2.schema.json`.

## Shape
- Result contract: optional `waiting: {"reason": "waiting_for_merge", "pr_url": "https://..."}`. A waiting result
  must be `ok: false` (it is not done) and so carries a `reason` like any `ok: false` result. Closed reason set;
  `pr_url` required, `https://`, no whitespace, bounded length. An older applier that ignores `waiting` therefore
  strict-stops (fail-safe) instead of completing the phase and running deploy.
- Waiting state lives in the LOOP STATE (`.shipwright/run_loop_state.json`, gitignored pointer file, not the WebUI
  schema), as a `waiting` marker keyed to run id + phase task id + task CAS version — the same pattern as the
  existing `gateTerminal` marker. The task in run_config simply stays `in_progress`. Loss of the loop state is
  safe: the task is re-dispatched, and the phase (U6) reports waiting again if the PR is still open.
- Recording a waiting result resets the task's dispatch `attempt` / `gateRejections` (a waiting pass is a finished
  pass, not a retry) so later gate rejections keep their full retry budget.

## Changes
1. `single_session/result_contract.py`: validate + build the `waiting` block (`WAITING_REASONS`).
2. `single_session/loop_state.py`: pure `record_waiting` / `waiting_for` / `clear_waiting` + `hold_waiting`.
3. New `orchestrator_pkg/single_session_wait.py`: `apply_waiting` (CAS check like the lifecycle's: stale version /
   session -> exit 2 reasons; not in_progress -> `invalid_status_for_completion`; else record the marker, emit
   `phase_waiting`), `waiting_action` (the `waiting` answer with `next_step` text), `resume_waiting` (resume card;
   `--confirm` clears the marker, emits `resume`).
4. `single_session_apply.py`: route a waiting result to `apply_waiting` after the override check (an override of a
   waiting result is refused `override_requires_ok_result`, as for any ok:false), before artifacts/gate/completion.
5. `single_session_loop.py`: `resolve_next_dispatch` answers `waiting` for a frontier with a current marker.
6. `single_session_recovery.resume_run`: a waiting frontier gives `action: resume` + `waiting` block; confirmed, the
   marker is cleared and `next` is a dispatch of the same task.
7. `single_session_cli.py`: `waiting` is an ok `next` action (exit 0). `observability`: `phase_waiting` event type.
8. `hooks/master_stop_check.py`: the in-progress banner names the waiting PR when the loop state holds a marker.
9. Docs: `single-session-loop.md`, `SKILL.md` (loop + resume), `agents/phase-runner.md` (result shape),
   `docs/hooks-and-pipeline.md`, `docs/guide.md` chapter 4.
10. Spec: FR-01.01 gains one AC (pre-build AC record, auto mode).
11. Tests (shipwright-run root): contract validation; apply/next/resume/stop-hook; an end-to-end loop test on a real
    run_config: changelog waits -> task in_progress, run in_progress, no deploy task, `next` = waiting with URL;
    resume confirm -> same task dispatched with a rotated version; ok -> deploy planned; and with
    `deploy_target: none` -> run complete.

## Not in scope
The changelog side emitting the result (U6). Multi-phase campaign loop (none needed). No new run_config status.

## Alternative approach considered
A new phase-task status `waiting` in run_config: needs a schema value (STRICT-STOP, WebUI reads the schema).
Encode waiting as `ok: true` + flag: an older applier would mark it done and run deploy.
