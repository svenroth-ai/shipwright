---
name: shipwright-run
description: "Pipeline Initializer & Phase Coordinator for the Shipwright SDLC pipeline. Writes the run spec, prints a phase launch card, then ends — each phase runs in its own external Claude session.\nTRIGGER when: user wants to run the full pipeline, start the complete SDLC process, build an entire application from scratch, or resume an interrupted pipeline. Also when user says 'shipwright run' or 'start the pipeline'.\nDO NOT TRIGGER when: user asks for a specific phase only (project, design, plan, build, test, deploy, changelog, compliance), or asks to fix/change/add something to an existing project (/shipwright-iterate). If the user wants only ONE phase, trigger that specific skill instead."
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

Security scanning is no longer part of the pipeline — run /shipwright-security
manually or activate .github/workflows/security.yml when ready.

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
uv run "{plugin_root}/scripts/lib/inference.py" \
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
Mode:       {multi_session (default) | single_session}
              multi_session = each phase its own external session; single_session = one driven conversation.
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
    - "Change mode"
    - "Skip deploy"
```

---

## Step 4: Write Pipeline Spec

```bash
uv run "{plugin_root}/scripts/lib/orchestrator.py" write-config \
  --scope "{scope}" \
  --profile "{profile}" \
  --autonomy "{autonomy}" \
  --mode "{mode}" \
  --deploy-target "{target}" \
  --project-root "$(pwd)"
```

`--mode` defaults to `multi_session`; pass `single_session` only if chosen in Step 3 (a mode-less legacy config reads as `multi_session`).

This writes `shipwright_run_config.json` at `schemaVersion: 2`. The orchestrator:

- Generates `runId` and freezes `runConditions`. Post-decouple, `securityEnabled` is always `false` (security is no longer an orchestrator phase). `aikidoClientIdPresent` is set from `AIKIDO_CLIENT_ID` for diagnostic purposes only — it does not gate any phase.
- Initializes `phase_tasks[]` with the first task: `{phase: "project", status: "awaiting_launch", sessionUuid: <pre-bound uuid4>, prerequisites: []}`.
- Subsequent phase tasks are appended by phase Stop hooks via `complete-phase-task` → `plan-next-phase`. **The master never plans phases directly.**

**Important — always pass `--profile`:** the WebUI Preview button keys off
`shipwright_run_config.json.profile` + the matching `shared/profiles/{name}.json`
to decide whether the project can launch a dev server. Omitting `--profile`
leaves the field null and Preview never appears. When Step 2 returns a
non-null profile, ALWAYS include it. For Next.js + Supabase (or Next.js as
default), pass `--profile supabase-nextjs`.

Capture the parsed JSON output — Step 5 reads `phase_tasks[0]` from it.

**Mode branch (SS3).** If `config.mode == "single_session"`, skip Step 5's
launch-card hand-off and drive the pipeline in THIS conversation via the
**[Single-Session Orchestrator Loop](references/single-session-loop.md)** (Step 5 + Resume Support are the `multi_session` default path).

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

## Step 5: Print Launch Card and End

The master is done. Read `phase_tasks[0]` from the config you just wrote and
render the **hand-off banner**, branched on the **launch surface**. A pipeline
phase launches as its own `claude --session-id …` session, so the hand-off
depends on whether this surface can start one.

**Compute these values:**

- `runId` → from `config.runId` (e.g. `run-a1b2c3d4`).
- `shortRunId` → first 4 hex chars after the `run-` prefix (e.g. `a1b2`).
- `phase` → `phase_tasks[0].phase` (always `"project"` for a fresh run).
- `splitId` → `phase_tasks[0].splitId` (always `null` at run init).
- `sessionUuid` → `phase_tasks[0].sessionUuid` (pre-bound uuid4).
- `slashCommand` → `phase_tasks[0].slashCommand` (`/shipwright-project` for run init).
- `projectRoot` → `$(pwd)` (the cwd you passed to `write-config`).
- `pipelineLength` → `len(config.pipeline)` (always 7 post-decouple — security is no longer an orchestrator phase).
- `nameSuffix` → `splitId ? f"{phase} / {splitId}" : phase` (here just `"project"`).
- `surface` → read `CLAUDE_CODE_ENTRYPOINT` (POSIX `printenv CLAUDE_CODE_ENTRYPOINT`;
  PowerShell `$env:CLAUDE_CODE_ENTRYPOINT`). `cli` (a plain shell OR the WebUI's
  embedded terminal, which re-sets `cli`) → `surface = terminal`. `claude-vscode`,
  a desktop-app value, or any GUI chat surface → `surface = chat` — it CANNOT
  start a bound `claude --session-id` phase session.

**Render the banner — branch on `surface`:**

**(a) `surface` is chat — VS Code extension or desktop app.** This chat surface
can't start a bound phase session, so the pipeline can't advance here. Tell the
truth and point at a surface that can.

```
================================================================================
PIPELINE PLANNED — {runId}
================================================================================
Phase 1 of {pipelineLength} ({phase}) is registered — but this surface can't
launch it. The pipeline runs each phase as its own bound session
(claude --session-id …), which the VS Code extension / desktop chat can't start.

Run it from a surface that can:
  • Terminal (CLI) — paste:
      claude --session-id {sessionUuid} --add-dir "{projectRoot}" --name 'Run-{shortRunId} / {nameSuffix}' '{slashCommand}'
  • WebUI Command Center — open the Task Board and Continue each phase.

For a single change without the full pipeline, /shipwright-iterate runs here.
================================================================================
```

**(b) `surface` is terminal — CLI or the WebUI's embedded terminal.** Offer both
continue paths (board or paste); `cli` covers both.

```
================================================================================
PIPELINE PLANNED — {runId}
================================================================================
Phase 1 of {pipelineLength} ({phase}) is registered and ready.

▸ In the WebUI Command Center? The pipeline is on the Task Board as a Run
  lane — use Continue on Phase 1 ({phase}) there. You can close this session.

▸ In a plain terminal? Open a NEW terminal and paste this command:

    claude --session-id {sessionUuid} --add-dir "{projectRoot}" --name 'Run-{shortRunId} / {nameSuffix}' '{slashCommand}'

This master session can be closed — pipeline state lives in
shipwright_run_config.json. Each phase plans the next on its own Stop hook.

When all phases complete, the final phase's Stop hook flips
run.status = "complete" — you do NOT need to reopen this master session.
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

(add `--force-status awaiting_launch` for re-launch, or `--force-status skipped` to
move on without that phase's output.)

Then re-invoke /shipwright-run to print a fresh launch card for the recovered phase
(or paste the WebUI's launch-card command if the WebUI Kanban is in use).
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

If `shipwright_run_config.json` exists at `schemaVersion: 2`:

1. Read `config.phase_tasks[]` and `config.runId`.
2. Find the **next launchable** task — the first task with
   `status == "awaiting_launch"` (in `phase_tasks[]` order).
3. Detect **stale tasks** — entries with `status == "in_progress"` whose
   `claimAttemptedAt` is older than ~1 hour. These typically indicate a
   crashed phase session that never ran the Stop hook.
4. Determine `surface` — read `CLAUDE_CODE_ENTRYPOINT` (same as Step 5).
   `terminal` continues via the board's **Continue** (WebUI) or the paste card
   (CLI); `chat` (VS Code extension / desktop) can't launch a bound phase — send
   the user to a terminal or the Command Center.

**Render a resume banner:**

```
================================================================================
RESUMING PIPELINE — {runId}
================================================================================
Status: {config.status}
Terminal: {N_terminal} / {N_total} phase tasks
Splits frozen: {len(splits_frozen)}

{if next_launchable:}
Next phase ready ({phase}{/splitId}):
  • Command Center — Continue it on the Task Board.
  • Terminal — paste:
      claude --session-id {sessionUuid} --add-dir "{projectRoot}" --name 'Run-{shortRunId} / {nameSuffix}' '{slashCommand}'
{if surface == chat:} This chat (VS Code extension / desktop) can't launch it — use a terminal or the Command Center.

{if stale_tasks:}
Stale (likely crashed) phase tasks:
  - {phase}{/splitId} (ptk={short}) claimed at {claimAttemptedAt}

  To recover, paste this in your terminal:
    uv run "{plugin_root}/scripts/lib/orchestrator.py" recover-phase-task --phase-task-id {phaseTaskId}

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
- [single-session-loop.md](references/single-session-loop.md) — SS3 in-conversation orchestrator loop (`mode: single_session`)
