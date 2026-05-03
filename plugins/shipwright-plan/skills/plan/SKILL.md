---
name: shipwright-plan
description: "Creates detailed implementation plans from spec files via research, interview, external LLM review, and TDD approach. Generates section-based plans for /shipwright-build.\nTRIGGER when: user wants to plan implementation, create an implementation plan, break down a spec into sections, plan how to build something, create a technical design, generate build sections, or plan test strategy for a spec.\nDO NOT TRIGGER when: user asks to implement or write code (/shipwright-build), run tests (/shipwright-test), fix a bug or make a small change (/shipwright-iterate), deploy (/shipwright-deploy), define requirements (/shipwright-project), or design UI mockups (/shipwright-design)."
license: MIT
compatibility: Requires uv (Python 3.11+), git repository recommended. Recommended: OPENROUTER_API_KEY (or GEMINI_API_KEY + OPENAI_API_KEY) for external LLM review in Step 5. If missing, the skill will ask you whether to skip external review and fall back to mandatory self-review.
---

# Shipwright Plan Skill

Creates detailed, section-based implementation plans from spec files.
Enhanced fork of deep-plan with E2E test plan generation and sprint tracking.

---

## CRITICAL: First Actions

**Governing rules:** Read and follow `shared/constitution.md` (ALWAYS / ASK FIRST / NEVER boundaries).

**BEFORE using any other tools**, do these in order:

### A. Print Intro Banner

```
================================================================================
SHIPWRIGHT-PLAN: Deep Planning
================================================================================
Creates detailed implementation plans from spec files.

Usage: /shipwright-plan @path/to/spec.md
   or: Invoked by /shipwright-run (orchestrator)

Output:
  - Implementation plan with sections (01-name.md, 02-name.md, ...)
  - SECTION_MANIFEST in plan.md
  - Optional: E2E test plan (claude-plan-e2e.md)

Requirements:
  - Spec file from /shipwright-project
  - Recommended: OPENROUTER_API_KEY (or GEMINI_API_KEY + OPENAI_API_KEY)
    for external LLM review. If missing, the skill will ask whether to
    skip external review and fall back to mandatory self-review.
================================================================================
```

### B. Validate Input

Check if user provided @file argument pointing to a spec markdown file.

If NO argument or invalid:
```
================================================================================
SHIPWRIGHT-PLAN: Spec File Required
================================================================================

This skill requires a path to a spec markdown file.

Example: /shipwright-plan @path/to/01-auth/spec.md

The spec file should be output from /shipwright-project.
================================================================================
```
**Stop and wait for user to re-invoke with correct path.**

### C. Detect Invocation Mode

Determine if running within the pipeline or standalone:

1. Read `shipwright_run_config.json` (if exists)
2. **Pipeline mode**: `status == "in_progress"` AND `current_step == "plan"`
   - Full pipeline integration (update orchestrator state, enforce gates)
3. **Standalone mode**: file missing OR `status == "complete"` OR `current_step != "plan"`
   - Skip pipeline state updates (no `orchestrator.py update-step` calls)
   - Skip upstream completion checks
   - Still produce all artifacts (`shipwright_plan_config.json`, section files)
   - **Mark artifacts**: When writing `shipwright_plan_config.json`, add `"mode": "standalone"` at the top level.
   - Print: `"Running in standalone mode — pipeline state will not be updated."`
4. If `status == "in_progress"` AND `current_step != "plan"`:
   - Warn: `"Pipeline is in progress at step {current_step}. Running /shipwright-plan out of sequence may cause issues."`
   - Ask user before continuing.

**Hook auto-install**: If `shipwright_run_config.json` exists but `.claude/settings.json` does not contain the `UserPromptSubmit` hook for `suggest_iterate.py`, install it now (one-time, idempotent).

Store the detected mode in a variable `invocation_mode` = `"pipeline"` | `"standalone"` for use in later steps.

### D. Discover Plugin Root

The SessionStart hook injects `SHIPWRIGHT_PLUGIN_ROOT=<path>` into your context.

**If `SHIPWRIGHT_PLUGIN_ROOT` is in your context**, use it directly as `plugin_root`.

**Only if NOT in context** (hook didn't run), fall back to search:
```bash
find "$(pwd)" -name "setup-planning-session.py" -path "*/shipwright-plan/scripts/checks/*" -type f 2>/dev/null | head -1
```
If not found: `find ~ -name "setup-planning-session.py" -path "*/shipwright-plan/scripts/checks/*" -type f 2>/dev/null | head -1`

The plugin_root is the directory two levels up from `scripts/checks/`.

### C2. Load Project Context (MANDATORY)

**Read these files NOW before proceeding.** This context ensures architecture, coding standards, and past decisions inform the implementation plan. Do NOT skip this step.

1. `CLAUDE.md` — stack, conventions, commands
2. `.shipwright/agent_docs/conventions.md` — coding standards, naming, patterns
3. `.shipwright/agent_docs/decision_log.md` — ALL architectural decisions (read the complete file)
4. `.shipwright/agent_docs/architecture.md` — app structure, component tree, data flow
5. Run: `git log --oneline -10` — recent commits

If a file does not exist, skip it but print a WARNING:
```
WARNING: Operating with reduced project context.
  Missing: {list of missing files}
  Plan quality may be affected — architectural decisions and conventions not loaded.
```

### D. Run Setup Script

```bash
uv run --project {plugin_root} {plugin_root}/scripts/checks/setup-planning-session.py \
  --file "{spec_file_path}" \
  --plugin-root "{plugin_root}" \
  --session-id "{SHIPWRIGHT_SESSION_ID}"
```

Parse the JSON output. Check for:

1. **`success == true`**: Proceed with workflow
2. **`mode == "resume"`**: Skip to `resume_from_step`
3. **`success == false`**: Report error and stop

### E. Load Config

Read `{plugin_root}/config.json` for external review and E2E settings.

Check for session-specific overrides in `{planning_dir}/shipwright_plan_config.json`.

**Early config:** Write a minimal plan config for phase tracking (enables session handoff if user stops early):
```bash
uv run "{plugin_root}/scripts/checks/write-plan-config.py" \
  --project-root "$(pwd)" --status in_progress
```
This will be overwritten with the full config at Step 9 (completion).

### F. Print Session Report

```
================================================================================
SESSION REPORT
================================================================================
Mode:              {new | resume}
Spec:              {spec_file}
Planning dir:      {planning_dir}
External review:   {available | missing_keys (will prompt) | user_disabled}
E2E test plan:     {enabled | disabled}
{Resume from:      Step {N} (if resuming)}
================================================================================
```

---

## Step 0: Phase Session Context Recovery

If your context contains a `=== SHIPWRIGHT-PIPELINE-CONTEXT ===` block (injected
by the SessionStart hook), you are part of an active `/shipwright-run` pipeline.
Parse `phaseTaskId` from that block and run as your very first action:

```bash
uv run "${SHIPWRIGHT_PLUGIN_ROOT}/../../shared/scripts/tools/get_phase_context.py" \
  --phase-task-id <phaseTaskId-from-context>
```

The tool prints structured JSON with `runId`, `phase`, `splitId`, `prerequisites`,
`runConditions`, and a `skill_artifacts_to_read` list. Read those artifacts
before proceeding so this phase session has full context for what came before.

If NO `PIPELINE-CONTEXT` block is present, this is a standalone invocation —
continue with Step 1 below as normal.

---

## Step 1: Research

See [research-protocol.md](references/research-protocol.md) for detailed guidance.

**Goal:** Understand the codebase, existing patterns, and technical landscape.

**Actions:**
1. Read the spec file thoroughly
2. If existing codebase: explore structure, read key files, understand patterns
3. If new project: review similar codebases, best practices
4. Use web search for unfamiliar technologies or patterns

**Checkpoint:** Mental model formed. No file written — research informs all subsequent steps.

---

## Step 2: Interview

See [interview-protocol.md](references/interview-protocol.md) for detailed guidance.

**Goal:** Surface design decisions, constraints, and preferences.

**Actions:**
1. Ask adaptive questions about architecture, data model, UX
2. Clarify ambiguities from spec
3. Identify risks and unknowns

**Checkpoint:** Write `{planning_dir}/shipwright_plan_interview.md` with full transcript.

**Write interview decisions to decision_log.md:**

After the interview, extract all architecture/design decisions made (e.g., UUID strategy,
component style, auth callback behavior, state management choice) and log each one:

```bash
uv run "{plugin_root}/../../shared/scripts/tools/write_decision_log.py" \
  --section "Plan Interview — {split_name}" \
  --commit "n/a" \
  --context "{why the question arose}" \
  --decision "{what was decided}" \
  --consequences "{impact on implementation}" \
  --rejected "{alternatives considered}"
```

Only log decisions that go **beyond** what the profile or project interview already decided.
Typical planning interview decisions: ORM vs raw SQL, component library variants, caching strategy, API patterns.

---

## Step 3: Context Check

See [context-check.md](references/context-check.md) for detailed guidance.

**Goal:** Before writing the plan, assess if context window is getting large.

Run the context check script:
```bash
uv run --project {plugin_root} {plugin_root}/scripts/checks/check-context-decision.py
```

If context is getting large, consider:
- Summarizing research findings before proceeding
- Writing a brief outline first for user approval

---

## Step 4: Plan Writing

See [plan-writing.md](references/plan-writing.md) and [tdd-approach.md](references/tdd-approach.md) for guidance.

**Goal:** Write the implementation plan as prose with TDD approach.

**Plan structure:**
- Overview of approach
- Section breakdown with SECTION_MANIFEST
- For each section: goals, implementation steps, test strategy
- Cross-cutting concerns

See [section-index.md](references/section-index.md) for the SECTION_MANIFEST format.

**Checkpoint:** Write `{planning_dir}/plan.md` with SECTION_MANIFEST block.

---

## Step 5: External LLM Review (Default + Fallback)

See [external-review.md](references/external-review.md) for protocol.

**Goal:** Get the plan reviewed for blind spots — either by external LLMs (default) or, if unavailable, by a mandatory self-review pass ("2x denken").

**This step is NOT optional.** One of the three branches below must run to completion, and the marker file `{planning_dir}/external_review_state.json` must be written. Step 6 is gated on that marker.

Read `external_review_status` from the session report (printed in First Actions > F). It is one of: `available`, `missing_keys`, `user_disabled`.

### Branch A — `external_review_status == "available"`

External review keys are present and `feedback_iterations > 0`. Run the full external review:

```bash
uv run --project {plugin_root} {shared_root}/scripts/tools/external_review.py \
  --mode plan \
  --plan-file "{planning_dir}/plan.md" \
  --spec-file "{spec_file}" \
  --plugin-root "{plugin_root}"
```

(`{shared_root}` resolves to the monorepo's `shared/` directory — typically
`{plugin_root}/../../shared`. The CLI consolidated into `shared/` in v0.5.x;
plan-mode prompts still load from `{plugin_root}/prompts/plan_reviewer/`.)

This runs Gemini and OpenAI reviews **in parallel** via ThreadPoolExecutor (OpenRouter when set, direct APIs otherwise).

**Process findings:**
1. Present both reviews to the user
2. Integrate accepted suggestions into `plan.md`
3. Mark each finding as addressed or declined (with reason)

**Write each finding to decision_log.md** via:
```bash
uv run "{plugin_root}/../../shared/scripts/tools/write_decision_log.py" \
  --section "External Review — {split_name}" \
  --commit "n/a" \
  --context "External LLM review finding: {finding summary}" \
  --decision "{accepted: what changed | rejected: why not}" \
  --consequences "{impact on plan}" \
  --rejected "{if accepted: original approach | if rejected: the suggestion itself}"
```

Then go to **Step 5b**.

### Branch B — `external_review_status == "missing_keys"`

`feedback_iterations > 0` but no API key was found in `.env.local`. **Stop** and ask the user verbatim:

> External LLM review is the recommended quality gate for this plan, but no `OPENROUTER_API_KEY` (or `GEMINI_API_KEY` / `OPENAI_API_KEY`) was found in `.env.local`.
>
> **Option 1 (recommended):** Add `OPENROUTER_API_KEY=...` to `.env.local` at the repo root and say "ready" — I'll re-check and run the external review.
> **Option 2:** Skip external review. I'll fall back to a mandatory self-review ("2x denken") pass and log the opt-out in the decision log.
>
> Which option?

Do NOT proceed until the user explicitly chooses.

- **User picks Option 1:** wait for their "ready" confirmation, then re-check:
  ```bash
  uv run --project {plugin_root} {shared_root}/scripts/checks/check-external-review-keys.py
  ```
  If `available: true`, fall into Branch A (run `review.py`, integrate, log, then Step 5b).
  If still `false`, ask the user again (they may have edited the wrong file or forgotten to save).
- **User picks Option 2:** run the **Self-Review Fallback** sub-block below. Capture their reason (e.g., "offline", "keys not yet provisioned") for the marker.

### Branch C — `external_review_status == "user_disabled"`

`feedback_iterations == 0` — explicit opt-out via config. Print:

```
External LLM review disabled via config (feedback_iterations: 0).
Running mandatory self-review fallback ("2x denken") instead.
```

Run the **Self-Review Fallback** sub-block.

### Self-Review Fallback (sub-block)

This is the "2x denken" pass. Re-read `plan.md` with a critic's eye and apply this checklist. For each item, write a 1–2 sentence finding to `plan.md` under a new `## Self-Review (2x denken)` section, integrate any corrections, and log each finding to `decision_log.md`.

1. **Architectural soundness:** Are there design decisions I would second-guess if I were reviewing someone else's plan? List concrete blind spots.
2. **Section boundaries:** Is each section self-contained? Are there hidden cross-dependencies that will surface during /shipwright-build?
3. **TDD coverage:** Does every section's test strategy validate behavior, or just implementation details?
4. **Risk hotspots:** What's the single riskiest section? What could go wrong? Is there a mitigation in the plan?
5. **Assumptions:** What assumptions did I make that the user did not explicitly confirm? List them and flag for user review.

**Output format (append to plan.md):**
```
## Self-Review (2x denken)
- **Architectural soundness:** {finding + action taken}
- **Section boundaries:** {finding + action taken}
- **TDD coverage:** {finding + action taken}
- **Risk hotspots:** {finding + action taken}
- **Assumptions:** {finding + action taken}
- **Status:** {all clear | {N} issues corrected | {N} issues flagged for user}
```

Log each non-trivial finding to `decision_log.md` using `write_decision_log.py` with `--section "Self-Review — {split_name}"`.

Then go to **Step 5b**.

### Step 5b: Mark review state

After exactly one branch completes, write the marker file so Step 6 can advance:

```bash
uv run --project {plugin_root} {shared_root}/scripts/checks/mark-review-state.py \
  --planning-dir "{planning_dir}" \
  --status "{completed | skipped_user_opt_out | skipped_config_disabled}" \
  --provider "{openrouter | gemini | openai | null}" \
  --findings-count {N} \
  --reason "{optional reason for skip}"
```

- Branch A → `--status completed --provider {actual provider}`
- Branch B Option 2 → `--status skipped_user_opt_out --reason "{user's reason}"`
- Branch C → `--status skipped_config_disabled`

**Checkpoint:** `{planning_dir}/external_review_state.json` exists.

---

## Step 6: Section Splitting

**Gate:** Read `{planning_dir}/external_review_state.json`. If missing, STOP — Step 5 was not completed. Return to Step 5 and pick the appropriate branch. If present, proceed.


See [section-splitting.md](references/section-splitting.md) for protocol.

**Goal:** Split plan into self-contained section files for /shipwright-build.

**Actions:**
1. Parse SECTION_MANIFEST from plan.md
2. Generate section tasks
3. For each section: spawn section-writer subagent OR write directly

**Batch approach (recommended for 3+ sections):**
```bash
uv run --project {plugin_root} {plugin_root}/scripts/checks/generate-batch-tasks.py \
  --planning-dir "{planning_dir}"
```

Each section file is written by the `shipwright-plan:section-writer` subagent.
The SubagentStop hook automatically captures output to the correct file.

**CRITICAL — JSONL Race Condition Fix (from upstream v0.3.1):**
The `write-section-on-stop.py` hook reads the subagent's JSONL transcript.
Claude Code may not have flushed the transcript when the hook fires.
The fix: retry with backoff (50ms, 100ms, 200ms) if transcript file is empty or incomplete.

**Checkpoint:** All section files exist in `{planning_dir}/sections/`.

---

## Step 7: Section Validation

Run section validation:
```bash
uv run --project {plugin_root} {plugin_root}/scripts/checks/check-sections.py \
  --planning-dir "{planning_dir}"
```

Verify all sections declared in SECTION_MANIFEST have corresponding files.

---

## Step 8: E2E Test Plan (Shipwright Enhancement — Optional)

**Runs if `e2e_test_plan.enabled` is true in config, OR if no config exists and the project has a UI** (i.e., `.shipwright/designs/screens/` contains HTML mockups, or `component_library` is set in profile). Default to enabled for UI projects.

See [e2e-test-plan.md](references/e2e-test-plan.md) for guidance.

**Goal:** Generate a Playwright E2E test plan based on the implementation plan.

**Actions:**
1. Read the full plan and all sections
2. Identify user-facing flows (login, CRUD, navigation)
3. Write test scenarios with expected outcomes
4. Include page object model suggestions

**Checkpoint:** Write `{planning_dir}/claude-plan-e2e.md`.

---

## Step 9: Completion

**Verification (all must pass before "phase complete"):**

1. plan.md exists with SECTION_MANIFEST
2. All declared sections have files
3. Interview transcript exists
4. E2E test plan exists (if enabled)
5. **Section Quality Gate** — for each section file, verify it contains:
   - Description (what the section implements)
   - Implementation Steps (at least 2 concrete steps)
   - Test Strategy (what tests to write)
   - If any section is missing these → fix before proceeding
6. **FR Coverage Check** — read the spec's Functional Requirements, verify every FR is assigned to at least one section. If uncovered FRs found → add them to appropriate section or create new section
7. **Dependency Order** — sections with dependencies must come after their dependencies in SECTION_MANIFEST

**Phase complete — update pipeline state:**

Iterate 12.2 brings the plan plugin to full Minimum Phase Completion
Canon (C1+C2+C3+C4 + `phase_history`). C1/C2/C4 were already in place;
C3 (canon-marker handoff) + `phase_history` append are new. **C5 is
skipped by policy** — plan is an internal decomposition artifact, not a
user-facing change (no CHANGELOG entry).

Set `SHIPWRIGHT_RUN_ID` at the top of this step so the C3 canon marker
and `phase_history` entry share one id. Missing env var → safe degrade
(stderr warning, no canon marker, Stop hook regenerates normally).

```bash
# If the orchestrator didn't already set it, derive one here:
export SHIPWRIGHT_RUN_ID="plan-$(date +%Y%m%d-%H%M%S)-{split_name}"

# Update plan config to complete
uv run "{plugin_root}/scripts/checks/write-plan-config.py" \
  --project-root "$(pwd)" --status complete --split "{split_name}" --sections {N}

# C1 — Record phase completion event (idempotent — skips if recorded).
uv run "{shared_root}/scripts/tools/record_event.py" \
  --project-root "$(pwd)" --type phase_completed --phase plan \
  --detail "{N} sections for {split_name}"

# C2 — Update delivery dashboard.
uv run "{shared_root}/scripts/tools/update_build_dashboard.py" \
  --project-root "$(pwd)" --phase plan --detail "{N} sections for {split_name}" \
  --session-id "{SHIPWRIGHT_SESSION_ID}"

# C3 (NEW 12.2) — Canon-marked session handoff.
uv run "{shared_root}/scripts/tools/generate_session_handoff.py" \
  --project-root "$(pwd)" --canon-marker --phase plan \
  --reason "plan complete: {split_name}, {N} sections"

# C4 — already written in Step 2 / Step 5 via write_decision_log.py
# (interview + external review decision ADRs). Nothing to do here.

# C5 — SKIPPED by policy (plan is internal decomposition, not user-facing).

# phase_history (NEW 12.2) — audit trail entry.
uv run "{shared_root}/scripts/tools/append_phase_history.py" \
  --project-root "$(pwd)" --phase plan --run-id "{SHIPWRIGHT_RUN_ID}" \
  --entry-json '{"split":"{split_name}","sections":{N},"outcome":"sectioned"}'

# Mark plan phase complete. _validate_plan() now runs the modular
# plan_checks verifier (plan_config status, section files, FR orphans,
# section id validity, canon, phase_history) — missing artifacts or
# drift blocks this call via ask-level issues.
uv run "{plugin_root}/../../plugins/shipwright-run/scripts/lib/orchestrator.py" \
  update-step --project-root "$(pwd)" --step plan --status complete
```
Where `{shared_root}` = `{plugin_root}/../../shared`.

**Print Summary:**
```
================================================================================
SHIPWRIGHT-PLAN COMPLETE
================================================================================
Plan:         {planning_dir}/plan.md
Sections:     {N} sections generated
Review:       {external via OpenRouter/Gemini/OpenAI | self-review fallback (user opt-out) | self-review fallback (config opt-out)}
E2E Plan:     {generated | skipped}

Section files:
  - sections/01-name.md
  - sections/02-name.md
  ...

Next steps:
  1. Review plan.md and section files
  2. Run /shipwright-build for each section:
     /shipwright-build @sections/01-name.md
     /shipwright-build @sections/02-name.md
     ...
================================================================================
```

---

## Error Handling

### Missing API Keys
Handled interactively in Step 5 Branch B. If no API key is detected in `.env.local`,
the skill STOPS and asks the user whether to add a key (Option 1) or opt out into
self-review fallback (Option 2). Never silently skipped.

```
Note (legacy): silent-skip behavior was removed. See Step 5 Branch B for the
current interactive flow.
```

### Section Writer Failure
If a section-writer subagent fails:
1. Log the error
2. Attempt to write the section directly (without subagent)
3. If still fails: mark section as incomplete, continue with others

### Context Window Pressure
If context is getting large during plan writing:
1. Save progress so far
2. Suggest user run `/clear` and resume
3. Session state allows resuming from any step

---

## Reference Documents

- [research-protocol.md](references/research-protocol.md) — Codebase and web research
- [interview-protocol.md](references/interview-protocol.md) — Stakeholder questions
- [context-check.md](references/context-check.md) — Context window management
- [plan-writing.md](references/plan-writing.md) — Plan writing guidelines
- [tdd-approach.md](references/tdd-approach.md) — Test-driven development planning
- [section-index.md](references/section-index.md) — SECTION_MANIFEST format
- [section-splitting.md](references/section-splitting.md) — Batch section generation
- [external-review.md](references/external-review.md) — External LLM review protocol
- [e2e-test-plan.md](references/e2e-test-plan.md) — Playwright E2E test plan (NEW)
