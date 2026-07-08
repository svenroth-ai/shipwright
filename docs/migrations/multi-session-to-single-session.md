# Migration: multi-session → single-session pipeline

**Since:** SS8 (Campaign `2026-07-07-single-session-pipeline`, 2026-07-08)

As of SS8, **single-session is the sole supported `/shipwright-run` pipeline
mode** and the default for every fresh run. The multi-session model — each phase
running as its own external UUID-bound `claude --session-id` session, advanced by
the `phase_session_stop` hook — is **deprecated** and retained only for
back-compat. Its code path removal is deferred (tracked separately); it is not
the default and receives no further investment.

## Why

Single-session runs the pipeline in ONE conversation (the master drives each
phase via a phase-runner subagent), so it works on **every** surface — CLI, the
WebUI Command Center, the VS Code extension, and desktop chat. Multi-session only
worked where a launcher could spawn a bound `claude --session-id` session
(CLI / WebUI), and it stalled in the extension/desktop chat.

## Do I need to migrate?

- **A fresh run** — nothing to do. A new `/shipwright-run` (or `write-config` with
  no explicit `--mode`) now selects `single_session` automatically.
- **An existing in-flight run** — a run that has no `mode` field (pre-SS1) or an
  explicit `mode: "multi_session"` keeps running as multi-session (the default
  flip does NOT silently reinterpret it). Migrate it with the steps below when you
  want it to finish under single-session.

## Migrating an in-flight run

1. **Make sure no phase session is actively running.** Close any open phase
   terminal (a live phase session claiming a task must not race the migration).
2. **Set the mode** in the project's `shipwright_run_config.json`:
   ```json
   "mode": "single_session"
   ```
3. **Resume the pipeline:** run `/shipwright-run` (the resume path). The
   single-session loop picks up at the current `phase_tasks` frontier and drives
   the remaining phases in the one conversation.

Single- and multi-session share the same `phase_tasks` state (both go through
`phase_task_lifecycle`), so the frontier — the current `awaiting_launch` /
`in_progress` phase task — carries over unchanged. No re-planning, no lost
progress.

### If a phase is wedged `in_progress`

If a phase was claimed by a phase session that crashed (left `in_progress` with a
dead session), recover it first, then resume:

```bash
uv run plugins/shipwright-run/scripts/lib/orchestrator.py recover-phase-task \
  --phase-task-id <the-in_progress-phaseTaskId> --project-root .
```

`recover-phase-task` releases the stale claim and bumps the CAS version, so the
old session can't complete it after you've moved on. Then resume as in step 3.

## Notes

- `--mode multi_session` still works for a deliberate legacy/back-compat run, but
  it is deprecated — expect it to be removed once single-session is battle-tested.
- The mode-less READ fallback stays `multi_session` on purpose: it protects
  existing runs from being reinterpreted mid-flight. Migration is always explicit.
