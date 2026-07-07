# Single-Session Orchestrator Loop (`mode: single_session`)

> Reached from Step 4 when the run config carries `mode: single_session`
> (Campaign 2026-07-07, SS3). In this mode the master does NOT print a launch
> card and step aside — it DRIVES every phase from this one conversation, the
> way a campaign drives sub-iterates. `multi_session` (the default) is
> unchanged: use Step 5's surface-aware hand-off.

## Why single_session

`multi_session` advances each phase from its own external `claude --session-id`
session (a phase Stop hook plans the next). Surfaces that can't start a bound
session — the VS Code extension, the desktop chat — therefore stall at phase 1.
`single_session` runs the whole pipeline in-conversation via a phase-runner
subagent per phase, so it advances on EVERY surface.

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
   - `wrong_mode` / `no_config` → not a single_session run; do not loop.

2. **Dispatch the `shipwright-run:phase-runner` subagent** for
   `dispatch.slashCommand` (the `phase` / `splitId`). Brief it with the phase
   context; it runs that ONE phase skill, **writes every real output to DISK
   itself** (it has a Write path — see `plugins/shipwright-run/agents/
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
  (`shared/config/gate_catalog.json`): under single_session an `auto-default`
  gate proceeds with no END-TURN; `orchestrator-approve` / `hard-stop` still
  stop for a human (constitution AskUserQuestion discipline). The loop just
  dispatches; a stopping gate surfaces as the phase pausing.
- **Splits** fan out SERIALLY in v1: plan/01 → build/01 → plan/02 → build/02 →
  test. There is no parallel split path.
- **Strict-stop:** any `ok:false` phase result halts the run with no successor.
  Recover with `recover-phase-task` (Step 6), then re-enter the loop.

## Resumability

Loop state persists to `.shipwright/run_loop_state.json` (distinct from the
campaign loop's `loop_state.json`); the authoritative per-phase status stays in
`shipwright_run_config.json`. If the master conversation dies mid-run, re-invoke
`/shipwright-run`, run `single-session-reload` to rebuild the compact pipeline
context, then resume the loop from `single-session-next` — a task left
`in_progress` (claimed but unapplied) is re-dispatched idempotently. (Deeper
recovery / observability is SS5.)
