# The Orchestrator Loop (`mode: single_session`)

> Step 5 of the master skill. The master DRIVES every phase from this one
> conversation, the way a campaign drives sub-iterates. `single_session` is the
> SOLE pipeline mode.

## Why the master drives

The pipeline used to advance each phase from its own external bound Claude
session, with a phase Stop hook planning the next one (`mode: multi_session`).
Surfaces that cannot start a bound session — the VS Code extension, the desktop
chat — therefore stalled at phase 1. That engine was removed in
iterate-2026-07-14-remove-multi-session. The master now runs the whole pipeline
in-conversation via one phase-runner subagent per phase, so it advances on EVERY
surface, and a run pauses/resumes with the master rather than fragmenting across
sessions.

## The loop

The master alternates two orchestrator subcommands with a phase-runner subagent
in between. Both reuse `phase_task_lifecycle` — there is **no bespoke completion
path** and the master **never mutates `shipwright_run_config.json` directly**.

Repeat until a terminal signal:

1. **Resolve + claim the next phase.**
   ```bash
   uv run "{plugin_root}/scripts/lib/orchestrator.py" single-session-next \
     --project-root "{project_root}"
   ```
   The JSON `action` is one of:
   - `dispatch` → a `dispatch` descriptor (`phaseTaskId`, `phase`, `splitId`,
     `sessionUuid`, `version`, `slashCommand`, `title`). The task is now claimed
     (in_progress) and a dispatch is recorded in loop state.
   - `complete` → the pipeline finished. Stop; print the completion summary.
   - `failed` → a phase strict-stopped (`failed_tasks`). Stop; surface it.
   - `needs_validation` → deploy done but tasks non-terminal (`blocked`). Stop.
   - `mode_unsupported` / `no_config` → not a drivable single-session run; do not
     loop. Print the returned `message` (a mode-less or removed-`multi_session`
     config migrates by setting `"mode": "single_session"` and re-invoking).

2. **Dispatch the `shipwright-run:phase-runner` subagent** for
   `dispatch.slashCommand` (the `phase` / `splitId`). Brief it with the phase
   context — **including `dispatch.phaseTaskId`, so it can load its prior-phase
   artifacts itself** via `get_phase_context.py --phase-task-id` (its Step 0; no hook can
   inject context into a subagent), and on a re-dispatch after a gate rejection the
   rejection's `issues[]` (step 3). It runs that ONE phase skill, **writes every real
   output to DISK itself** (it has a Write path — see `plugins/shipwright-run/agents/
   phase-runner.md`), and returns a compact phase-runner RESULT CONTRACT (see
   `plugins/shipwright-run/scripts/lib/single_session/result_contract.py`):
   `{ok, phase, summary, artifacts[], reason?, splitId?, review_status?}`. The `summary` is
   capped at `MAX_SUMMARY_CHARS`; real outputs go to DISK (`artifacts`), never
   into the result. Persistence is the runner's own responsibility — it does NOT
   rely on a Stop hook (the failure that lost a section-writer's output).

   **Read `review_status` before applying.** `deferred` / `partial` /
   `skipped` means the phase's review cascade did not fully run (the runner's
   spawn failed or it was skipped; `reason_code` says why): the master runs the
   missing passes itself (it has the `Agent` tool) or surfaces them in the final
   summary — never treat the phase as fully reviewed. Absent `review_status` =
   nothing reported (older runner, or no cascade).

3. **Apply the result.** Write the returned JSON to a file, then:
   ```bash
   uv run "{plugin_root}/scripts/lib/orchestrator.py" single-session-apply \
     --phase-task-id "{dispatch.phaseTaskId}" \
     --session-uuid "{dispatch.sessionUuid}" \
     --version {dispatch.version} --result-json "{path}" \
     --project-root "{project_root}"
   ```
   This validates the contract, **verifies on disk that every artifact an
   `ok:true` result claims actually exists** (a claimed-but-unwritten artifact is
   rejected `artifacts_missing`, no completion — the persistence guarantee),
   freezes splits when a design phase completes (so build fans out per split),
   routes the result through `complete_phase_task` (an `ok:false` result
   strict-stops via `mark_phase_failed`, planning NO successor), and advances the
   loop pointer. The `next` field carries the resolved next action — loop on it.

   **The phase gate.** Between the artifact check and the completion, apply runs the
   phase's own validators and canon checks (`orchestrator_pkg/phase_gate.py`) — the gate
   is **enforced by default**. When it finds ask-level issues, apply answers `ok:false`,
   `reason: "phase_gate_failed"`: the task stays `in_progress` and only the rejection is
   counted (loop state `gateRejections`). Never complete a phase with the raw
   `complete-phase-task` — it is refused (`use_single_session_apply`). On a pass, relay
   any `gate.inform` notes (warnings, not blockers) to the person: they are returned, not
   stored. Handle a rejection by its `terminal`:
   - `terminal: null` → a retry is due. Call `single-session-next` (it re-dispatches the
     same task and counts the dispatch), then brief the phase-runner again **with
     `issues[]`** — the rejection's `issues` copied verbatim as data — so it fixes those
     findings and re-applies.
   - `terminal: "ask_human"` (guided, after `MAX_GATE_RETRIES` = 2 retries, or at once
     when `retryable: false` — a broken or incomplete check install, or a Phase-Quality
     critical-gate finding, that re-running cannot fix). Stop and ask, in plain words,
     with the issues listed: **go ahead anyway** (offer it only when the rejection says
     `override_allowed: true`) → re-apply the same result with
     `--override-reason "<their reason>"`; **give it more
     tries** → `single-session-recover` (fresh retry count), then `single-session-next`;
     **stop the run** → `orchestrator.py mark-phase-failed` with the issues as `--error`.
   - autonomous runs take the failed terminal themselves: apply returns the normal
     strict-stop (`ok:true`, `run_status: "failed"`, `next.action: "failed"`) with a `gate`
     block naming the issues. Surface it as any failed run (Step 6); it is recoverable
     with `single-session-recover`.

   **Send every retry through `single-session-next`.** The cap counts the task's dispatches
   (`run_loop_state.json.attempt`, including a crash-resume re-dispatch) and its gate
   rejections (`gateRejections`), whichever is higher, and both reset when the loop moves on
   or the task is recovered. Without a loop state for this task (a library apply that never
   went through `single-session-next`) the position is unknown and nothing is capped. A gate
   that passes adds `gate: {result, checked, issues, inform}` to the
   success payload; inform notes there are not persisted.

   **Override (ASK FIRST).** `--override-reason "<why>"` on `single-session-apply` completes
   a phase over its gate: the gate still runs, and its findings, the reason, the task and
   the run's autonomy are written to `validation_overrides[]` in the same locked write as
   the completion. A blank reason, an `ok:false` result and any autonomy other than
   `guided` / `autonomous` (so `unattended`, a typo, or none at all) are refused. That
   refusal only stops a cooperative caller: use it **only on a person's explicit answer** —
   never because retries ran out — and never brief a phase-runner to call it.

   On resume, the master rebuilds pipeline context with a third subcommand:
   ```bash
   uv run "{plugin_root}/scripts/lib/orchestrator.py" single-session-reload \
     --project-root "{project_root}"
   ```
   It returns `{ok, context:{runId, status, mode, splitsFrozen, phaseSummaries[],
   summaryCharBudget}}` — built from `shipwright_run_config.json` + the compact
   `phase_tasks[].result` summaries, never a phase transcript (bounded context
   regardless of run length).

## Gates, splits, failures

- **Gates** are honored INSIDE each phase skill via the SS2 gate policy
  (`shared/config/gate_catalog.json`): in a driven single-session run an
  `auto-default` gate proceeds with no END-TURN; `orchestrator-approve` /
  `hard-stop` still stop for a human (constitution AskUserQuestion discipline).
  The mechanism is inert (every gate `interactive`) for any config that is not an
  explicit `mode: single_session` run — a standalone or adopted project is
  unaffected. The loop just
  dispatches; a stopping gate surfaces as the phase pausing. When a phase pauses
  at an `orchestrator-approve` / `hard-stop` gate, record it for observability +
  loop-state:
  ```bash
  uv run "{plugin_root}/scripts/lib/orchestrator.py" single-session-gate \
    --phase-task-id "{dispatch.phaseTaskId}" --phase "{dispatch.phase}" \
    --state pause --project-root "{project_root}"   # (--state resume after approval)
  ```
  This flips loop-state `paused_human_gate` ⇄ `running` and emits a
  `human_gate_pause` / `human_gate_resume` event. (Optional bookkeeping — the loop
  advances the same either way.)
- **Splits** fan out SERIALLY in v1: plan/01 → build/01 → plan/02 → build/02 →
  test. There is no parallel split path.
- **Strict-stop:** any `ok:false` phase result (and an autonomous gate terminal) halts
  the run with no successor. Recover with `single-session-recover` (Step 6), then
  re-enter the loop; re-applying an `ok:true` result to a failed task is refused
  (`invalid_status_for_completion`, exit 2).

## Resumability (SS5)

Loop state persists to `.shipwright/run_loop_state.json` (distinct from the
campaign loop's `loop_state.json`); the authoritative per-phase status stays in
`shipwright_run_config.json`.

**If the master conversation dies mid-run, just re-invoke `/shipwright-run`.**
Step 4 detects `mode: single_session` + a live loop-state on a non-terminal run and
resumes via a **confirm card** rather than starting fresh:

1. **Read the resume decision (read-only — no side effects):**
   ```bash
   uv run "{plugin_root}/scripts/lib/orchestrator.py" single-session-resume \
     --project-root "{project_root}"
   ```
   Returns `{action, resumeAction, loopState, context, next}`. `action` is:
   - `resume` → print the card: last-done (`loopState.lastCompletedPhaseTaskId`),
     current (`loopState.currentPhaseTaskId`), `attempt`, and what resuming will do
     (`resumeAction`, always `dispatch`). Ask the user **Resume vs Abandon** (constitution
     AskUserQuestion). This call CLAIMS nothing and emits nothing — Abandon leaves
     state clean.
   - `complete` / `failed` / `needs_validation` → the run already FINISHED — not
     resumable. Surface it (a `failed` run recovers via `single-session-recover`, then
     resume); do not loop. No event is emitted.
   - `runid_mismatch` → the persisted loop-state belongs to a DIFFERENT run than the
     current `run_config` (a stale pointer from a prior aborted run). Do NOT resume;
     surface both run ids.
   - `mode_unsupported` / `no_config` → not a drivable single-session run; do not
     resume. Print the returned `message` (the fix is to set
     `"mode": "single_session"` and re-invoke).
   - `not_resumable` → single_session but nothing was ever dispatched; start the loop
     normally from `single-session-next`.
2. **On Resume, commit it** (records the `resume` event) and re-enter the loop:
   ```bash
   uv run "{plugin_root}/scripts/lib/orchestrator.py" single-session-resume \
     --confirm --project-root "{project_root}"
   ```
   Then continue from **step 1 of the loop** (`single-session-next`): a task left
   `in_progress` (claimed but unapplied when the master died) is re-dispatched
   **idempotently** — `single-session-next` re-claims it by its own `sessionUuid`
   (`idempotent: true`, `executionCount` NOT re-bumped) and the SS4 artifact
   persistence-guard still verifies its outputs on apply.

**Why idempotent re-run is safe here.** The phase-runner is a SUBAGENT of the master
conversation, so when the master dies the runner dies with it — there is no orphaned
live worker to race on resume. (Split-brain WAS a real hazard under the removed
`multi_session` mode, whose phases ran as independent external Claude processes that
outlived the master; removing that mode removed the hazard with it.)
`recover-phase-task` stays the manual escape for a truly wedged task; in the loop use
`single-session-recover` (same lifecycle mutator + a `recovery` event + loop-pointer
realign).

## Observability

The loop appends structured telemetry to `.shipwright/run_loop_events.jsonl` (append-only
JSONL, gitignored, distinct from the tracked pipeline `shipwright_events.jsonl`). Event
types: `dispatch`, `phase_result`, `strict_stop`, `human_gate_pause`,
`human_gate_resume`, `resume`, `recovery`. Emission is **best-effort** — a config that
is not a drivable single-session run never reaches these paths (so it never grows the
file), and a telemetry write failure never crashes the loop (it warns to stderr).

The durable, tracked `phase_started` / `phase_completed` pairs in
`shipwright_events.jsonl` are emitted by the loop CLI itself
(`single-session-next` → `record_phase_started`, `single-session-apply` →
`record_phase_end`), one per split. They used to have a second producer in the
`phase_session_start` hook; with that hook gone the loop is the SOLE producer.
