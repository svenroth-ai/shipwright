# Migration: multi-session → single-session pipeline

**Status: multi-session is REMOVED.** `single_session` is the sole `/shipwright-run`
pipeline mode. This note is the terminal migration record — the message you get from a
stale run config points here.

## What changed

`/shipwright-run` used to be a *coordinator*: it wrote the run spec, printed a
paste-able `claude --session-id <uuid> …` launch card, and ended. Each phase then ran as
**its own external bound Claude session**, which claimed and completed its phase task
through a trio of hooks (`phase_session_start` → `phase_user_prompt_validate` →
`phase_session_stop`). That was `mode: multi_session`.

The master now **drives** the pipeline: it runs each phase as a **phase-runner subagent
inside its own conversation**, applying each result and planning the next until the run
is terminal. That is `mode: single_session`.

The external per-phase-session engine — the three hooks above plus their private helpers
(`phase_context_blocks.py`, `lib/hook_session.py`, `lib/phase_event_emit.py`) — has been
**deleted**, and the hooks are deregistered from all 8 phase plugins.

## Why

A bound `claude --session-id` session can only be spawned from a surface that has a
launcher — a terminal, or the WebUI Command Center. The Claude Code **VS Code extension
and desktop chat cannot**, so `/shipwright-run` simply stalled at phase 1 there.
Single-session has no such dependency: a subagent runs wherever its parent runs, so the
pipeline advances on **every** surface. A run also now pauses and resumes with the
master, instead of fragmenting across sessions that can outlive it.

## Do I need to migrate?

- **A fresh run** — no. `/shipwright-run` writes `mode: single_session` for you.
- **An existing run config** — yes, if it records `mode: "multi_session"`, or records no
  `mode` at all (a pre-SS1 config). Either way it is **not** silently reinterpreted:
  every execution entry point refuses it up front, with the message that sent you here.

## How to migrate

1. **Make sure no phase session is still running.** Close any open phase terminal left
   over from the old model — a live phase session must not race the migration.

2. **Set the mode** in the project's `shipwright_run_config.json`:

   ```json
   "mode": "single_session"
   ```

3. **Resume:** run `/shipwright-run`. It prints a resume card and continues from the
   current `phase_tasks` frontier, driving the remaining phases in the one conversation.

**No phase work is lost.** `phase_tasks[]` is the same structure in both models — the
single-session loop calls the *same* `phase_task_lifecycle` mutators the deleted Stop
hook called. The frontier (the current `awaiting_launch` / `in_progress` task) carries
over unchanged: no re-planning, no lost progress. A task left `in_progress` is re-claimed
**idempotently** (by its own `sessionUuid`, which is a CAS claim token, not a Claude
session id), and the artifact persistence-guard still verifies its outputs on apply.

### If a phase is wedged `in_progress`

If a phase was claimed by a phase session that crashed, recover it first, then resume:

```bash
uv run plugins/shipwright-run/scripts/lib/orchestrator.py recover-phase-task \
  --phase-task-id <the-in_progress-phaseTaskId> --project-root .
```

`recover-phase-task` releases the stale claim and bumps the CAS version, so the old
session can't complete it after you've moved on. Then resume as in step 3.

## Why the refusal is loud rather than automatic

A mode-less config *could* have been auto-read as `single_session` — it is, after all,
the only mode left. It deliberately isn't:

- **Drivability is an explicit literal.** A run is a driven pipeline **iff** its config
  records `mode: "single_session"`. The orchestrator loop and the phase-gate policy apply
  the identical test, so they can never disagree about whether a run is being driven.
- That symmetry is what makes the removal safe. `multi_session` used to double as the
  *"this is not a single-session run"* sentinel that kept phase gates `interactive` for
  standalone and adopted projects. Inferring a mode for configs that never declared one
  would have quietly flipped those projects into auto-answering their gates. The sentinel
  survives the removal under an honest name (`gate_policy.INERT_MODE = "standalone"`),
  and nothing is inferred.

Reading a stale config still works — the guard sits on the **execution** path, never the
read path — so historical runs stay inspectable in the WebUI and under
`.shipwright/runs/**`.
