---
name: shipwright-run
description: "Master orchestrator for the Shipwright SDLC pipeline. From user description to deployed application. Use this as the single entry point: /shipwright-run"
license: MIT
compatibility: Requires uv (Python 3.11+), git. Optional: JELASTIC_TOKEN for deploy.
---

# Shipwright Run — The Orchestrator

Single entry point for the entire Shipwright SDLC pipeline.

---

## CRITICAL: First Actions

### A. Print Intro Banner

```
================================================================================
SHIPWRIGHT-RUN: AI-Powered Software Delivery
================================================================================
From description to deployed application.

Usage:
  /shipwright-run "Build a SaaS time tracker with Supabase"
  /shipwright-run                        (interactive)
  /shipwright-run --iterate "Add dark mode toggle"
  /shipwright-run @requirements.md

Pipeline: Project → Design → Plan → Build → Test → Deploy → Changelog
================================================================================
```

### B. Detect Input & Mode

**Iteration mode** (`--iterate`):
- User has an existing project (CLAUDE.md exists)
- Quick change: 1-2 questions, 1 split, 1-2 sections
- Skip to [Iteration Flow](#iteration-flow)

**Full mode** (default):
- New project or major extension
- Continue to Step 1

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
| **Scope** | New project (no CLAUDE.md) → Full App; existing CLAUDE.md → Extension |
| **Profile** | "Supabase" + "Next.js" → `supabase-nextjs`; no match → ask user |
| **Autonomy** | Default: `guided` (ask at key decisions); user can choose `autonomous` |

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
Deploy to:  {Jelastic DEV | none}

Accept or modify:
================================================================================
```

```
AskUserQuestion:
  question: "Settings look correct?"
  options:
    - "Accept — start building"
    - "Change profile"
    - "Change autonomy"
    - "Skip deploy"
```

---

## Step 4: Write Config

```bash
uv run {plugin_root}/scripts/lib/orchestrator.py write-config \
  --scope "{scope}" \
  --profile "{profile}" \
  --autonomy "{autonomy}" \
  --deploy-target "{target}" \
  --project-root "$(pwd)"
```

Writes `shipwright_run_config.json`:
```json
{
  "scope": "full_app",
  "profile": "supabase-nextjs",
  "autonomy": "guided",
  "deploy_target": "jelastic-dev",
  "pipeline": ["project", "design", "plan", "build", "test", "deploy", "changelog"],
  "status": "in_progress",
  "current_step": "project"
}
```

---

## Step 5: Execute Pipeline

### Full Application Flow

The orchestrator dispatches to each skill in sequence:

```
1. /shipwright-project    → Requirements → Splits + Specs
2. /shipwright-design     → Specs → UI Mockups (HTML)
3. For each split:
   a. /shipwright-plan    → Spec → Sections
   b. For each section:
      - /shipwright-build → Section → Code + Tests + Commit
   c. /shipwright-test    → Run all tests
   d. /shipwright-deploy  → Deploy to DEV
4. /shipwright-changelog  → Changelog + PR
```

**Between each skill:**
- Update `shipwright_run_config.json` with progress
- Update compliance documentation (incremental):
  ```bash
  uv run {compliance_plugin_root}/scripts/tools/update_compliance.py \
    --project-root "$(pwd)" --phase "{completed_phase}"
  ```
  Where `{compliance_plugin_root}` = `{plugin_root}/../../shipwright-compliance` (sibling plugin)
- Check if context window is getting large → suggest `/clear` + resume

**Guided mode:** Ask user at each major transition:
```
AskUserQuestion:
  question: "Project phase complete. {N} splits created. Continue to design?"
  options:
    - "Continue"
    - "Review first"
    - "Stop here"
```

**Autonomous mode:** Continue without asking (except PROD deploy and destructive operations).

### Extension Flow

Same pipeline but lighter:
- shipwright-project: Extension scope (1-3 questions, usually 1 split)
- Rest of pipeline identical

### Invoking Skills

Each skill is invoked as a slash command:
```
/shipwright-project @{planning_dir}/requirements.md
/shipwright-design @{split_dir}/spec.md
/shipwright-plan @{split_dir}/spec.md
/shipwright-build @{sections_dir}/01-name.md
/shipwright-test
/shipwright-deploy
/shipwright-changelog
```

The orchestrator reads config files written by each skill to determine:
- What the next step is
- Which splits/sections are remaining
- Whether to proceed or ask user

---

## Step 6: Completion

```
================================================================================
SHIPWRIGHT-RUN: COMPLETE
================================================================================
Scope:      {Full Application | Extension}
Profile:    {supabase-nextjs}
Splits:     {N} completed
Sections:   {M} implemented
Tests:      {passed}/{total} passing
Deploy:     {DEV URL | skipped}
Changelog:  {version | skipped}
PR:         {PR URL | skipped}

Project artifacts:
  - CLAUDE.md
  - agent_docs/ (architecture, conventions, decision_log, sprint, handoff)
  - CHANGELOG.md
  - compliance/ (dashboard, RTM, test evidence, change history, SBOM)
  - shipwright_*_config.json files
================================================================================
```

---

## Iteration Flow

When invoked with `--iterate`:

### 1. Read Existing Context
- Read `CLAUDE.md` and `agent_docs/`
- Read `shipwright_run_config.json` (reuse profile, deploy target)

### 2. Understand Change
- User describes what to change: "Add dark mode toggle"
- 1-2 clarifying questions max

### 3. Light Decomposition
- Skip full interview
- 1 split, 1-2 sections
- Reuse existing profile and conventions

### 4. Execute Pipeline
Same as Full App but shorter:
```
/shipwright-project "Add dark mode toggle"    → 1 split
/shipwright-plan @01-dark-mode/spec.md        → 1-2 sections
/shipwright-build @sections/01-theme.md       → implement
/shipwright-test                              → verify
/shipwright-deploy                            → deploy to DEV
/shipwright-changelog                         → changelog + PR
```

---

## Resume Support

If the pipeline is interrupted (context window, user stops, error):

1. Read `shipwright_run_config.json` → `current_step`
2. Read per-plugin configs → determine exact resume point
3. Skip completed steps
4. Continue from where we left off

---

## Reference Documents

- [inference-rules.md](references/inference-rules.md) — Scope + profile inference
- [autonomy-levels.md](references/autonomy-levels.md) — Guided vs autonomous behavior
- [scope-flows.md](references/scope-flows.md) — Full App, Extension, Iterate flows
