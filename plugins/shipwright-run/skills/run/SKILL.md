---
name: shipwright-run
description: "Pipeline Initializer & Phase Coordinator for the Shipwright SDLC pipeline. Writes the run spec, then DRIVES every phase from this one conversation via a phase-runner subagent.\nTRIGGER when: user wants to run the full pipeline, start the complete SDLC process, build an entire application from scratch, or resume an interrupted pipeline. Also when user says 'shipwright run' or 'start the pipeline'.\nDO NOT TRIGGER when: user asks for a specific phase only (project, design, plan, build, test, deploy, changelog, compliance), or asks to fix/change/add something to an existing project (/shipwright-iterate). If the user wants only ONE phase, trigger that specific skill instead."
license: MIT
compatibility: Requires uv (Python 3.11+), git. Optional: JELASTIC_TOKEN for deploy.
---

# Shipwright Run — The Pipeline Coordinator

Single entry point for the entire Shipwright SDLC pipeline. The master session
**specs** the pipeline (writes `shipwright_run_config.json`), then **drives** it:
resolve the next phase → dispatch a phase-runner subagent → apply its result →
repeat, until the pipeline is terminal.

Because every phase runs as a subagent of *this* conversation, the pipeline
advances on **every surface** — CLI, VS Code extension, desktop app. There is no
launch card to paste and no second session to open.

---

## CRITICAL: First Actions

**Governing rules:** Read and follow `shared/constitution.md` (ALWAYS / ASK FIRST / NEVER boundaries).

### A. Print Intro Banner

```
================================================================================
SHIPWRIGHT-RUN: AI-Powered Software Delivery
================================================================================
From description to deployed application.

Usage:
  /shipwright-run "Build a SaaS time tracker with Supabase"
  /shipwright-run                        (interactive)
  /shipwright-run @requirements.md

Pipeline: Project → Design → Plan → Build → Test → Changelog → Deploy

Security scanning is out-of-band — run /shipwright-security or activate .github/workflows/security.yml.

This session DRIVES the pipeline: each phase runs as a phase-runner subagent
right here. Keep it open — closing it pauses the run (re-invoke to resume).

For ongoing changes to existing projects, use /shipwright-iterate instead.

In plain words (shared index → docs/guide.md Appendix A):
  IREB-Spec: Description of what the app should do, who it's for, and what it must not do
  ADR: Log of architectural decisions with rationale (why this database, why this pattern)
================================================================================
```

### B. Detect Input & Mode

**Full mode** (default):
- New project or major extension
- Continue to Step 1

If `shipwright_run_config.json` already exists at `schemaVersion: 2`, this is a
**resume** — jump to [Resume Support](#resume-support) below before continuing
the new-pipeline flow.

### C. Discover Plugin Root

The SessionStart hook injects `SHIPWRIGHT_PLUGIN_ROOT=<path>`. Use it directly.

---

## Step 1: Understand Intent

**Goal:** Figure out what the user wants to build.

**Input sources (in priority order):**
0. **Brief** (WebUI Intent Wizard): a pre-delivered file/payload with the four
   wizard answers → run [brief-intake.md](references/brief-intake.md), ask ONLY what's missing.
1. **File**: `@requirements.md` → read and summarize
2. **Inline**: `"Build a SaaS time tracker..."` → use as starting context
3. **Chat**: No input → ask: "What do you want to build?"

Ask 1-3 clarifying questions if the description is vague (skip any the brief
already answered): core feature · who are the users · tech preferences.

---

## Step 2: Infer Settings

See [inference-rules.md](references/inference-rules.md). If Step 1 ran a brief,
[brief-intake.md](references/brief-intake.md) already fixed profile + deploy — reuse them; infer only fields left null.

```bash
uv run "{plugin_root}/scripts/lib/inference.py" \
  --description "{user_description}"
```

The inference engine determines:

| Setting | How Inferred |
|---------|-------------|
| **Scope** | New project (no CLAUDE.md) → Full App; existing CLAUDE.md → Extension. For ongoing changes, use `/shipwright-iterate`. |
| **Profile** | "Supabase" + "Next.js" → `supabase-nextjs`; no match → ask user |
| **Autonomy** | Default: `guided` (phases stop at gates for you); user can choose `autonomous` |

---

## Step 3: Confirm Settings

Present inferred settings and allow override:

```
================================================================================
INFERRED SETTINGS
================================================================================
Scope:      {Full Application | Extension}
Profile:    {supabase-nextjs | custom}
Autonomy:   {guided | autonomous}
              Guided:     Phases ask before destructive actions.
              Autonomous: Phases run hands-off (Deploy still asks).
Deploy to:  {Jelastic DEV | none}

Accept or modify:
================================================================================
```

```
AskUserQuestion:
  question: "Settings look correct?"
  options:
    - "Accept — write pipeline spec"
    - "Change profile"
    - "Change autonomy"
    - "Skip deploy"
```

There is no execution-mode question: `single_session` is the sole pipeline mode.

---

## Step 4: Write Pipeline Spec

```bash
uv run "{plugin_root}/scripts/lib/orchestrator.py" write-config \
  --scope "{scope}" \
  --profile "{profile}" \
  --autonomy "{autonomy}" \
  --deploy-target "{target}" \
  --project-root "$(pwd)"
```

This writes `shipwright_run_config.json` at `schemaVersion: 2` with
`mode: single_session` (the sole mode — `--mode` exists but has exactly one
valid value). The orchestrator:

- Generates `runId` and freezes `runConditions`. Post-decouple, `securityEnabled` is always `false` (security is no longer an orchestrator phase). `aikidoClientIdPresent` is set from `AIKIDO_CLIENT_ID` for diagnostic purposes only — it does not gate any phase.
- Initializes `phase_tasks[]` with the first task: `{phase: "project", status: "awaiting_launch", prerequisites: []}`. Each task carries a pre-bound `sessionUuid` — the **CAS claim token** the loop claims it with, not a Claude session id.
- Subsequent phase tasks are appended by `complete-phase-task` → `plan-next-phase` as each phase finishes. **The master never plans phases directly** — it drives the loop; the lifecycle plans.

**Important — always pass `--profile`:** the WebUI Preview button keys off
`shipwright_run_config.json.profile` + `shared/profiles/{name}.json` to decide
whether Preview can launch a dev server. Omitting it leaves the field null and
Preview never appears — always include the Step 2 profile (Next.js/Supabase → `supabase-nextjs`; local-only default → `vite-hono`).

Capture the parsed JSON output — Step 5 reads `runId` from it.

---

## Step 4.5: Phase-Router Hook (no install step needed)

The `suggest_iterate.py` UserPromptSubmit hook is registered in
`shipwright-iterate` plugin's own `hooks/hooks.json`; no project-level
`.claude/settings.json` install is performed. Once the user enables
the `shipwright-iterate@shipwright` plugin (default in marketplace
installs), the hook fires automatically for every prompt in any project
carrying `shipwright_run_config.json`. ADRs 019/020 (carrier-shape Shape B +
quoted path + `--no-project`) survive verbatim in the plugin registration.

**Legacy adopt cleanup:** if `.claude/settings.json` carries an old
`UserPromptSubmit` entry referencing `${CLAUDE_PLUGIN_ROOT}/.../suggest_iterate.py`,
Claude Code shows a "hook is not associated with a plugin" error (that variable
only expands in plugin context). One-time fix: drop that one
`hooks.UserPromptSubmit` entry from `.claude/settings.json`; the
plugin-registered hook still fires.

---

## Step 5: Drive the Pipeline

Announce the run, then enter the loop:

```
================================================================================
PIPELINE RUNNING — {runId}
================================================================================
Phase 1 of {pipelineLength} ({phase}) starting.

I drive every phase from this conversation — nothing to paste, nothing to open.
Keep this session alive: closing it pauses the run. Re-invoke /shipwright-run to
resume exactly where it stopped (no phase work is lost).
================================================================================
```

Then run the **[Single-Session Orchestrator Loop](references/single-session-loop.md)**:
alternate `single-session-next` (resolve + claim the frontier phase) and
`single-session-apply` (validate + complete the phase-runner's result), with a
`shipwright-run:phase-runner` subagent in between, until a terminal signal
(`complete` / `failed` / `needs_validation`).

`pipelineLength` = `len(config.pipeline)` (always 7 post-decouple — security is
no longer an orchestrator phase).

**Do NOT** invoke a phase slash command directly and do NOT call
`orchestrator update-step`. The loop's two subcommands are the only way phases
advance — they reuse `phase_task_lifecycle`, so there is no bespoke completion path.

The master's own Stop hook (`master_stop_check.py`) is observational and prints a
summary to stderr. It does not change pipeline state.

---

## Step 6: Final Wrap-Up

Reached when the loop returns a terminal signal (or when the user re-opens the
master on an already-terminal config). Informational; it invokes no skill.

Read `shipwright_run_config.json`, then branch on `config.status`:

**`status == "complete"`:**

```
================================================================================
SHIPWRIGHT-RUN: COMPLETE — {runId}
================================================================================
Scope:      {scope}
Profile:    {profile}
Phases:     {N} terminal ({done} done, {skipped} skipped)
Splits:     {len(splits_frozen)} frozen
Deploy:     {deploy_target}

Project artifacts:
  - CLAUDE.md
  - .shipwright/agent_docs/ (architecture, conventions, decision_log, session_handoff, build_dashboard)
  - CHANGELOG.md
  - .shipwright/compliance/ (RTM, test evidence, change history, SBOM, dashboard)
  - shipwright_*_config.json files

For ongoing changes, use /shipwright-iterate.
================================================================================
```

**`status == "failed"`:**

```
================================================================================
SHIPWRIGHT-RUN: FAILED — {runId}
================================================================================
Failed phase tasks:
  - {phase}{/splitId} (ptk={short}) errors:
    - {error_line}

To recover, paste this in your terminal:

  uv run "{plugin_root}/scripts/lib/orchestrator.py" recover-phase-task --phase-task-id {phaseTaskId}

(add `--force-status awaiting_launch` to re-run that phase, or `--force-status skipped`
to move on without its output.)

Then re-invoke /shipwright-run — the loop picks up from the recovered phase.
================================================================================
```

**`status == "needs_validation"`:**

```
================================================================================
SHIPWRIGHT-RUN: COMPLETION BLOCKED — {runId}
================================================================================
Deploy completed, but other phase tasks are non-terminal:
  - {phase}{/splitId} (ptk={short}) status={status}

To resolve, paste this in your terminal (one command per non-terminal task):

  uv run "{plugin_root}/scripts/lib/orchestrator.py" recover-phase-task --phase-task-id {ptk} --force-status skipped

After all tasks are terminal, the next complete-phase-task call will
flip run.status to "complete".
================================================================================
```

**`status == "in_progress"`:** fall through to [Resume Support](#resume-support).

---

## Resume Support

The master conversation IS the driver, so a closed/crashed master is simply a
paused run. Re-invoking `/shipwright-run` on an existing `schemaVersion: 2`
config resumes it — see
[single-session-loop.md § Resumability](references/single-session-loop.md#resumability-ss5)
for the full protocol.

1. Read the resume decision (**read-only** — claims nothing, emits nothing):
   ```bash
   uv run "{plugin_root}/scripts/lib/orchestrator.py" single-session-resume \
     --project-root "{project_root}"
   ```
2. Branch on `action`:
   - `resume` → print the resume card (last-done phase, current phase, `attempt`,
     and what resuming will do), then ask the user **Resume vs Abandon**
     (constitution AskUserQuestion). On Resume, re-run with `--confirm` and
     re-enter the loop at Step 5.
   - `complete` / `failed` / `needs_validation` → the run already finished →
     [Step 6](#step-6-final-wrap-up).
   - `not_resumable` → single-session but nothing was ever dispatched → start the
     loop normally (Step 5).
   - `runid_mismatch` → the persisted loop-state belongs to a DIFFERENT run. Do
     NOT resume; surface both run ids.
   - `mode_unsupported` → this config is not a drivable single-session run (a
     mode-less pre-SS1 config, or one still carrying the **removed**
     `multi_session` mode). Print the returned `message`: the fix is to set
     `"mode": "single_session"` in `shipwright_run_config.json` and re-invoke.
     `phase_tasks[]` are shared and re-claim is idempotent, so no phase work is
     lost. See `docs/migrations/multi-session-to-single-session.md`.
   - `no_config` → not a pipeline run.

**Render a resume banner:**

```
================================================================================
RESUMING PIPELINE — {runId}
================================================================================
Status: {config.status}
Terminal: {N_terminal} / {N_total} phase tasks
Splits frozen: {len(splits_frozen)}

Last completed: {loopState.lastCompletedPhaseTaskId}
Resuming at:    {phase}{/splitId} (attempt {attempt})

A phase left in_progress (the master died mid-phase) is re-dispatched
idempotently — the phase-runner was a subagent of the dead master, so no
orphaned worker can race this resume.
================================================================================
```

---

## Reference Documents

- [single-session-loop.md](references/single-session-loop.md) — the orchestrator loop (Step 5), gates, splits, resume, observability
- [inference-rules.md](references/inference-rules.md) — Scope + profile inference
- [brief-intake.md](references/brief-intake.md) — WebUI-wizard brief → profile/env, ask only what's missing (K2c)
- [autonomy-levels.md](references/autonomy-levels.md) — Guided vs autonomous behavior (within phases)
- [scope-flows.md](references/scope-flows.md) — Full App and Extension flows
