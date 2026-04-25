---
name: shipwright-run
description: "Master orchestrator for the Shipwright SDLC pipeline. Specs the pipeline, prints a phase launch card, then ends — each phase runs in its own external Claude session.\nTRIGGER when: user wants to run the full pipeline, start the complete SDLC process, build an entire application from scratch, or resume an interrupted pipeline. Also when user says 'shipwright run' or 'start the pipeline'.\nDO NOT TRIGGER when: user asks for a specific phase only (project, design, plan, build, test, deploy, changelog, compliance), or asks to fix/change/add something to an existing project (/shipwright-iterate). If the user wants only ONE phase, trigger that specific skill instead."
license: MIT
compatibility: Requires uv (Python 3.11+), git. Optional: JELASTIC_TOKEN for deploy.
---

# Shipwright Run — The Pipeline Coordinator

Single entry point for the entire Shipwright SDLC pipeline. The master session
**specs** the pipeline (writes `shipwright_run_config.json`), prints a launch
card for the first phase, and then ends. Each phase runs in its own external
Claude CLI session — phase Stop hooks plan the next phase automatically. The
master session is **not** a pipeline driver; it is a coordinator that writes
the contract and steps aside.

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
          (Security inserted after Test when AIKIDO_CLIENT_ID is set)

Each phase runs in its own external Claude CLI session.
This master session writes the pipeline spec, prints the first
launch card, then ends — phase Stop hooks plan the next phase.

For ongoing changes to existing projects, use /shipwright-iterate instead.
================================================================================
```

### B. Detect Input & Mode

**Full mode** (default):
- New project or major extension
- Continue to Step 1

If `shipwright_run_config.json` already exists at `schemaVersion: 2`, this is a
**resume** — jump to [Resume Support](#resume-support) below before continuing
the new-pipeline flow.

> **Note:** For ongoing changes to existing projects (quick features, bug fixes, small changes), use `/shipwright-iterate` instead of `/shipwright-run`.

### C. Discover Plugin Root

The SessionStart hook injects `SHIPWRIGHT_PLUGIN_ROOT=<path>`. Use it directly.

---

## Step 1: Understand Intent

**Goal:** Figure out what the user wants to build.

**Input sources (in priority order):**
1. **File**: `@requirements.md` → read and summarize
2. **Inline**: `"Build a SaaS time tracker..."` → use as starting context
3. **Chat**: No input → ask: "What do you want to build?"

Ask 1-3 clarifying questions if the description is vague:
- What's the core feature?
- Who are the users?
- Any specific technology preferences?

---

## Step 2: Infer Settings

See [inference-rules.md](references/inference-rules.md) for logic.

```bash
uv run {plugin_root}/scripts/lib/inference.py \
  --description "{user_description}"
```

The inference engine determines:

| Setting | How Inferred |
|---------|-------------|
| **Scope** | New project (no CLAUDE.md) → Full App; existing CLAUDE.md → Extension. For ongoing changes, use `/shipwright-iterate`. |
| **Profile** | "Supabase" + "Next.js" → `supabase-nextjs`; no match → ask user |
| **Autonomy** | Default: `guided` (per-phase user prompts within each phase session); user can choose `autonomous` |

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
              Guided:     Phase sessions ask before destructive actions.
              Autonomous: Phase sessions run hands-off (Deploy still asks).
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

---

## Step 4: Write Pipeline Spec

```bash
uv run {plugin_root}/scripts/lib/orchestrator.py write-config \
  --scope "{scope}" \
  --profile "{profile}" \
  --autonomy "{autonomy}" \
  --deploy-target "{target}" \
  --project-root "$(pwd)"
```

This writes `shipwright_run_config.json` at `schemaVersion: 2`. The orchestrator:

- Generates `runId` and freezes `runConditions` (e.g. `securityEnabled` from `AIKIDO_CLIENT_ID`).
- Initializes `phase_tasks[]` with the first task: `{phase: "project", status: "awaiting_launch", sessionUuid: <pre-bound uuid4>, prerequisites: []}`.
- Subsequent phase tasks are appended by phase Stop hooks via `complete-phase-task` → `plan-next-phase`. **The master never plans phases directly.**

**Important — always pass `--profile`:** the WebUI Preview button keys off
`shipwright_run_config.json.profile` + the matching `shared/profiles/{name}.json`
to decide whether the project can launch a dev server. Omitting `--profile`
leaves the field null and Preview never appears. When Step 2 returns a
non-null profile, ALWAYS include it. For Next.js + Supabase (or Next.js as
default), pass `--profile supabase-nextjs`.

Capture the parsed JSON output — Step 5 reads `phase_tasks[0]` from it.

---

## Step 4.5: Install Phase-Router Hook

The `suggest_iterate.py` hook routes post-pipeline user prompts to
`/shipwright-iterate` instead of re-running the master. Because the master
never re-runs after completion under multi-session, install the hook **now**,
right after writing the spec — not at completion.

Check if `.claude/settings.json` in the project root already contains the
`UserPromptSubmit` hook for `suggest_iterate.py`. If not, add it:

```json
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "type": "command",
        "command": "uv run {shared_root}/scripts/hooks/suggest_iterate.py"
      }
    ]
  }
}
```

Where `{shared_root}` = `{plugin_root}/../../shared`.

---

## Step 5: Print Launch Card and End

The master is done. Read `phase_tasks[0]` from the config you just wrote and
render the launch card for the user to paste into a fresh terminal.

**Compute these values:**

- `runId` → from `config.runId` (e.g. `run-a1b2c3d4`).
- `shortRunId` → first 4 hex chars after the `run-` prefix (e.g. `a1b2`).
- `phase` → `phase_tasks[0].phase` (always `"project"` for a fresh run).
- `splitId` → `phase_tasks[0].splitId` (always `null` at run init).
- `sessionUuid` → `phase_tasks[0].sessionUuid` (pre-bound uuid4).
- `slashCommand` → `phase_tasks[0].slashCommand` (`/shipwright-project` for run init).
- `projectRoot` → `$(pwd)` (the cwd you passed to `write-config`).
- `pipelineLength` → `len(config.pipeline)` (7 baseline, 8 with security).
- `nameSuffix` → `splitId ? f"{phase} / {splitId}" : phase` (here just `"project"`).

**Render the banner:**

```
================================================================================
PIPELINE PLANNED — {runId}
================================================================================
Phase 1 of {pipelineLength} ({phase}) is ready to launch.

Open a NEW terminal and paste this command:

  claude --session-id {sessionUuid} --add-dir "{projectRoot}" --name 'Run-{shortRunId} / {nameSuffix}' '{slashCommand}'

This master session can be closed — pipeline state lives in
shipwright_run_config.json. Each phase will plan the next on its
own Stop hook.

When all phases complete, the final phase's Stop hook flips
run.status = "complete" — you do NOT need to reopen this master
session for the pipeline to finish.
================================================================================
```

**End the turn here.** Do NOT invoke any slash command, do NOT spawn a Task,
do NOT call orchestrator update-step. The master's job is done — phase Stop
hooks take over from this point.

The master's own Stop hook (`master_stop_check.py`) is observational and prints
a summary to stderr. It does not change pipeline state.

---

## Step 6: Final Wrap-Up (only on resume)

This step runs **only if** the user re-opens the master session on an existing
v2 config. It is informational; it does not invoke any skill.

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
  - agent_docs/ (architecture, conventions, decision_log, sprint, handoff)
  - CHANGELOG.md
  - compliance/ (RTM, test evidence, change history, SBOM, dashboard)
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

Recover with:
  uv run {plugin_root}/scripts/lib/orchestrator.py recover-phase-task \
    --phase-task-id {phaseTaskId} [--force-status awaiting_launch|skipped]

Then re-launch the relevant phase from the launch card in the WebUI.
================================================================================
```

**`status == "needs_validation"`:**

```
================================================================================
SHIPWRIGHT-RUN: COMPLETION BLOCKED — {runId}
================================================================================
Deploy completed, but other phase tasks are non-terminal:
  - {phase}{/splitId} (ptk={short}) status={status}

Resolve via:
  uv run {plugin_root}/scripts/lib/orchestrator.py recover-phase-task \
    --phase-task-id {ptk} --force-status skipped

After all tasks are terminal, the next complete-phase-task call will
flip run.status to "complete".
================================================================================
```

**`status == "in_progress"`:** fall through to [Resume Support](#resume-support).

---

## Resume Support

If `shipwright_run_config.json` exists at `schemaVersion: 2`:

1. Read `config.phase_tasks[]` and `config.runId`.
2. Find the **next launchable** task — the first task with
   `status == "awaiting_launch"` (in `phase_tasks[]` order).
3. Detect **stale tasks** — entries with `status == "in_progress"` whose
   `claimAttemptedAt` is older than ~1 hour. These typically indicate a
   crashed phase session that never ran the Stop hook.

**Render a resume banner:**

```
================================================================================
RESUMING PIPELINE — {runId}
================================================================================
Status: {config.status}
Terminal: {N_terminal} / {N_total} phase tasks
Splits frozen: {len(splits_frozen)}

{if next_launchable:}
Next phase ready to launch:

  claude --session-id {sessionUuid} --add-dir "{projectRoot}" --name 'Run-{shortRunId} / {nameSuffix}' '{slashCommand}'

{if stale_tasks:}
Stale (likely crashed) phase tasks:
  - {phase}{/splitId} (ptk={short}) claimed at {claimAttemptedAt}

  Recover with:
    uv run {plugin_root}/scripts/lib/orchestrator.py recover-phase-task \
      --phase-task-id {phaseTaskId}

  Then re-launch the relevant phase.
================================================================================
```

If no `awaiting_launch` task exists and no stale tasks: pipeline is either
in-progress (user is running a phase elsewhere — check the WebUI Kanban) or in
one of the terminal states handled by Step 6.

**Do not** invoke any slash command or modify state. Master stays a coordinator.

---

## Reference Documents

- [inference-rules.md](references/inference-rules.md) — Scope + profile inference
- [autonomy-levels.md](references/autonomy-levels.md) — Guided vs autonomous behavior (within phase sessions)
- [scope-flows.md](references/scope-flows.md) — Full App and Extension flows
