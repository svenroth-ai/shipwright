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

For ongoing changes to existing projects, use /shipwright-iterate instead.
================================================================================
```

### B. Detect Input & Mode

**Full mode** (default):
- New project or major extension
- Continue to Step 1

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
  "pipeline": ["project", "design", "plan", "build", "test", "changelog", "deploy"],
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
   [After build: orchestrator loops back to plan if more splits remain]
4. /shipwright-test       → Run all tests (full codebase, all splits merged)
5. /shipwright-security   → Security scan (if AIKIDO_CLIENT_ID set)
6. /shipwright-changelog  → Changelog + PR + Merge (aggregated across all splits)
7. /shipwright-deploy     → Deploy to DEV (from merged main, all splits)
8. /shipwright-compliance → Final compliance report generation (all artifacts)
```

**Important:** Steps 3a-3b repeat for EACH split. After build completes for one split,
`orchestrator.py update-step --step build --status complete` automatically detects remaining
splits and loops back: resets plan+build steps and sets `current_step` to "plan".
Test, changelog, and deploy run ONCE after all splits are built.

### Compliance Phase (Final)

After deploy completes (or is skipped), invoke:
```
/shipwright-compliance
```
This generates the final, complete compliance package. Incremental updates during the
pipeline are still useful for monitoring, but this final run ensures all reports
reflect the deployed state. The phase validator (INFORM level) will note which
artifacts were generated and which may need attention.

### Split Transition (automatic after build)

After build completes for a split, the orchestrator's `update-step` checks `get-build-progress`:
- If `all_done == false`: Resets plan+build steps, sets `current_step = "plan"`, resets tool counter
- If `all_done == true`: Pipeline continues to test → changelog → deploy (once)

When a split transition occurs, print:
```
================================================================================
SPLIT COMPLETE: {completed_split}
================================================================================
Completed: {N}/{total} splits built
Next: {next_split_name}
Continuing to /shipwright-plan...
================================================================================
```

Then continue the pipeline — the orchestrator will invoke `/shipwright-plan` for the next split's spec.

**Between each skill:**
- **Phase Validation & Completion:** After a skill finishes, mark the step complete:
  ```bash
  uv run {plugin_root}/scripts/lib/orchestrator.py \
    update-step --project-root "$(pwd)" --step "{completed_step}" --status complete
  ```
  Parse the returned JSON. **If `status == "needs_validation"`:** the phase produced incomplete artifacts.
  For each issue in `validation_issues`:
  ```
  AskUserQuestion:
    question: "{issue.message}"
    options:
      - "Fix this first"
      - "Continue anyway"
  ```
  - If user says **"Continue anyway"**: Re-call with `--force`:
    ```bash
    uv run {plugin_root}/scripts/lib/orchestrator.py \
      update-step --project-root "$(pwd)" --step "{step}" --status complete --force
    ```
  - If user says **"Fix this first"**: Print what needs to be fixed and **STOP**.
    The pipeline will auto-resume from this step on next `/shipwright-run`.

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
- **Reset tool call counter** (prevents stale counts from triggering false checkpoints in next phase):
  ```bash
  uv run {shared_root}/scripts/tools/reset_tool_counter.py
  ```
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
/shipwright-changelog
/shipwright-deploy
```

### Build Phase Autopilot Loop

See `references/build-autopilot.md` for the complete autopilot loop (section iteration, subagent delegation, guided mode prompts, dashboard updates).

### Test Phase Execution

See `references/test-execution.md` for the complete test execution flow (subagent delegation, result parsing, validation, dashboard updates).

### Security Scan (conditional)

`/shipwright-security` runs **only if `AIKIDO_CLIENT_ID` is set** (check via environment variable). If the variable is not set, skip silently — no error, no warning.

**In guided mode:** Always ask before running:
```
AskUserQuestion:
  question: "Tests passed. Run Aikido security scan before changelog/deploy?"
  options:
    - "Yes — run security scan"
    - "Skip — go to changelog"
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
3. If `current_step == "plan"` and `completed_steps` includes `project` and `design`:
   - This is a **split-loop resume** (not the first run)
   - Read `shipwright_build_config.json` → `current_split` to identify which split is next
   - Read `shipwright_project_config.json` → `splits[]` to get the spec path for this split
   - Print split-loop resume banner showing which split is starting
   - Continue to `/shipwright-plan` for the current split's spec
4. For other steps: skip completed steps, continue from `current_step`
5. Read `agent_docs/session_handoff.md` if it exists — use it for additional context about what was in progress

---

## Reference Documents

- [inference-rules.md](references/inference-rules.md) — Scope + profile inference
- [autonomy-levels.md](references/autonomy-levels.md) — Guided vs autonomous behavior
- [scope-flows.md](references/scope-flows.md) — Full App and Extension flows
