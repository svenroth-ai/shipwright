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
              Guided:     Interactive through all phases incl. Build and Test
                          with confirmation between phases and request for approval of fixes
              Autonomous: Interactive through Spec and Design with autonomous
                          Build and Test incl. fixes. Deploy stays interactive.
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
   d. /shipwright-security → Security scan (if AIKIDO_CLIENT_ID set)
   e. /shipwright-deploy  → Deploy to DEV
4. /shipwright-changelog  → Changelog + PR
```

**Between each skill:**
- **Upstream Success Check:** Before starting the next phase, verify the previous phase completed successfully:
  - Read `shipwright_run_config.json` → check that the previous phase status is `"complete"`
  - If previous phase is NOT complete → do NOT proceed. Inform user which phase failed and why.
  - This prevents cascading failures (e.g., building from an incomplete plan)
- Update `shipwright_run_config.json` with progress
- Update compliance documentation (incremental):
  ```bash
  uv run {compliance_plugin_root}/scripts/tools/update_compliance.py \
    --project-root "$(pwd)" --phase "{completed_phase}"
  ```
  Where `{compliance_plugin_root}` = `{plugin_root}/../../shipwright-compliance` (sibling plugin)
- **Update delivery dashboard** with pipeline progress:
  ```bash
  uv run {shared_root}/scripts/tools/update_build_dashboard.py \
    --project-root "$(pwd)" --phase "{completed_phase}" \
    --session-id "{SHIPWRIGHT_SESSION_ID}"
  ```
  Where `{shared_root}` = `{plugin_root}/../../shared`
- **Context pressure check** (after each skill completes):
  ```bash
  uv run {shared_root}/scripts/tools/estimate_context_pressure.py \
    --counter-file "$(pwd)/.shipwright_toolcall_count" --threshold 120
  ```
  If `recommend_checkpoint` is true:
  1. Generate session handoff
  2. Update build dashboard with `--status paused`
  3. Print checkpoint banner and **STOP**:
  ```
  ================================================================================
  CHECKPOINT — Context pressure detected
  ================================================================================
  Progress: {completed}/{total} sections complete
  Dashboard: agent_docs/build_dashboard.md

  To continue:
    1. Open a new session (+ button) <- recommended
    2. Or: /clear in this session

  Then invoke: /shipwright-run
    -> Auto-resumes from current position
  ================================================================================
  ```

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
/shipwright-security              (conditional, see below)
/shipwright-deploy
/shipwright-changelog
```

### Build Phase Autopilot Loop

When executing the build phase (step 3b in the pipeline), use the autopilot loop:

1. **Get section progress:**
```bash
uv run {plugin_root}/scripts/lib/orchestrator.py get-build-progress \
  --project-root "$(pwd)"
```

2. **Initialize dashboard:**
```bash
uv run {shared_root}/scripts/tools/update_build_dashboard.py \
  --project-root "$(pwd)" --session-id "{SHIPWRIGHT_SESSION_ID}"
```

3. **For each incomplete section** (from `next_section` in progress output):

   a. **Reset tool counter** (prevents stale counter from prior section):
      ```bash
      uv run {shared_root}/scripts/tools/reset_tool_counter.py \
        --counter-file "$(pwd)/.shipwright_toolcall_count"
      ```

   b. Update dashboard: `--section "{section}" --step 1 --detail "Starting"`

   **--- Autonomous mode: Subagent delegation ---**

   c. **IF autonomy == "autonomous":** Spawn `section-builder` subagent (Agent tool):
      - `description`: "Build section {section}"
      - `subagent_type`: "shipwright-build:section-builder"
      - `prompt`: Provide all required parameters:
        - `section_file`: `{sections_dir}/{section}.md` (absolute path)
        - `project_root`: `$(pwd)` (absolute path)
        - `plugin_root`: `{build_plugin_root}` (sibling: `{plugin_root}/../shipwright-build`)
        - `shared_root`: `{shared_root}` (= `{plugin_root}/../../shared`)
        - `branch_prefix`: from `shipwright_run_config.json`
        - `section_name`: `{section}`
        - `session_id`: `{SHIPWRIGHT_SESSION_ID}`
      - Do **NOT** use `run_in_background` — sections must be sequential
      - Do **NOT** use `isolation: "worktree"` — section N+1 needs section N's code

   d. **Parse subagent result JSON.** Expected fields:
      - `status`: "complete" or "failed"
      - `commit`, `branch`, `tests_passed`, `tests_total`, `review_findings`, `decisions`

   e. **If status == "failed":**
      - Update dashboard with `--status failed`
      - Print error summary from result
      - **STOP** — do not continue to next section
      - Inform user of failure with diagnosis from result

   f. **If status == "complete":**
      - Verify section state in config:
        ```bash
        uv run {shared_root}/scripts/tools/update_build_dashboard.py \
          --project-root "$(pwd)" --section "{section}" --status complete \
          --session-id "{SHIPWRIGHT_SESSION_ID}"
        ```
      - Log decisions from result to decision log (if any)
      - **No context pressure check needed** — subagent used its own context window
      - Continue to next section

   **--- Guided mode: Direct invocation (unchanged) ---**

   g. **IF autonomy == "guided":**
      - Invoke: `/shipwright-build @{sections_dir}/{section}.md`
      - On return: update dashboard with `--status complete`
      - Check context pressure:
        ```bash
        uv run {shared_root}/scripts/tools/estimate_context_pressure.py \
          --counter-file "$(pwd)/.shipwright_toolcall_count" --threshold 120
        ```
      - If `recommend_checkpoint` is true:
        - Update dashboard with `--status paused`
        - Generate session handoff
        - Print checkpoint banner (see above) and **STOP**

   h. Re-run `get-build-progress` and continue with next section

4. **All sections done:** Proceed to test phase (see below)

**In guided mode:** Ask before each section:
```
AskUserQuestion:
  question: "Section {N-1} complete ({completed}/{total}). Continue with {next_section}?"
  options:
    - "Continue"
    - "Review first"
    - "Stop here"
```

### Test Phase Execution

After all build sections are complete:

**--- Autonomous mode: Subagent delegation ---**

**IF autonomy == "autonomous":** Spawn `test-runner` subagent (Agent tool):
- `description`: "Run test suite"
- `subagent_type`: "shipwright-test:test-runner"
- `prompt`: Provide all required parameters:
  - `project_root`: `$(pwd)` (absolute path)
  - `plugin_root`: `{test_plugin_root}` (sibling: `{plugin_root}/../shipwright-test`)
  - `shared_root`: `{shared_root}`
  - `profile`: from `shipwright_project_config.json`
  - `session_id`: `{SHIPWRIGHT_SESSION_ID}`
  - `dev_url`: from `shipwright_build_config.json` → `dev_url`, or env `SHIPWRIGHT_DEV_URL`, or default `http://localhost:3000`

**Parse test-runner result JSON.** Expected fields:
- `status`: "pass" or "fail"
- `unit`: `{passed, total, duration_s}`
- `smoke`: `{status, url, response_ms}`
- `e2e`: `{passed, total, failures, skipped}`
- `fixes_applied`: list of auto-fixes attempted

**If status == "fail":**
- Update dashboard: `--phase test --status failed`
- Print test failure summary from result
- **STOP** — do not proceed to deploy
- Inform user of which tests failed and why

**If status == "pass":**
- Update pipeline state:
  ```bash
  uv run {plugin_root}/scripts/lib/orchestrator.py \
    update-step --project-root "$(pwd)" --step test --status complete
  ```
- Update dashboard:
  ```bash
  uv run {shared_root}/scripts/tools/update_build_dashboard.py \
    --project-root "$(pwd)" --phase test \
    --detail "{unit.passed}/{unit.total} unit, {e2e.passed}/{e2e.total} E2E" \
    --session-id "{SHIPWRIGHT_SESSION_ID}"
  ```
- Update compliance:
  ```bash
  uv run {compliance_plugin_root}/scripts/tools/update_compliance.py \
    --project-root "$(pwd)" --phase test
  ```
- Continue to security scan / deploy

**--- Guided mode: Direct invocation (unchanged) ---**

**IF autonomy == "guided":** Invoke `/shipwright-test` as before.

### Security Scan (conditional)

`/shipwright-security` runs **only if `AIKIDO_CLIENT_ID` is set** (check via environment variable). If the variable is not set, skip silently — no error, no warning.

**In guided mode:** Always ask before running:
```
AskUserQuestion:
  question: "Tests passed. Run Aikido security scan before deploy?"
  options:
    - "Yes — run security scan"
    - "Skip — go to deploy"
```

**In autonomous mode:** Run automatically (no prompt).

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

1. Read `shipwright_run_config.json` → `current_step` and `completed_steps`
2. If `current_step == "build"`:
   a. Run `orchestrator.py get-build-progress` → get section status
   b. **Validate split state:** If `current_split` in progress output doesn't match the split that owns the current sections, the split archive may have been missed. Run:
      ```bash
      uv run {shared_root}/scripts/tools/archive_split.py \
        --project-root "$(pwd)" --next-split "{correct_split_name}"
      ```
   c. Print resume banner:
   ```
   ================================================================================
   RESUMING PIPELINE
   ================================================================================
   Pipeline step: build
   Sections: {completed}/{total} complete
   Resuming from: {next_section}
   Dashboard: agent_docs/build_dashboard.md
   ================================================================================
   ```
   d. Enter Build Phase Autopilot Loop from first incomplete section
3. For other steps: skip completed steps, continue from `current_step`
4. Read `agent_docs/session_handoff.md` if it exists — use it for additional context about what was in progress

---

## Reference Documents

- [inference-rules.md](references/inference-rules.md) — Scope + profile inference
- [autonomy-levels.md](references/autonomy-levels.md) — Guided vs autonomous behavior
- [scope-flows.md](references/scope-flows.md) — Full App, Extension, Iterate flows
