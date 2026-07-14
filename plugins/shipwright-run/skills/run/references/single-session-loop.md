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
   inject context into a subagent). It runs that ONE phase skill, **writes every real
   output to DISK itself** (it has a Write path — see `plugins/shipwright-run/agents/
   phase-runner.md`), and returns a compact phase-runner RESULT CONTRACT (see
   `plugins/shipwright-run/scripts/lib/single_session/result_contract.py`):
   `{ok, phase, summary, artifacts[], reason?, splitId?}`. The `summary` is
   capped at `MAX_SUMMARY_CHARS`; real outputs go to DISK (`artifacts`), never
   into the result. Persistence is the runner's own responsibility — it does NOT
   rely on a Stop hook (the failure that lost a section-writer's output).

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
- **Strict-stop:** any `ok:false` phase result halts the run with no successor.
  Recover with `recover-phase-task` (Step 6), then re-enter the loop.

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
