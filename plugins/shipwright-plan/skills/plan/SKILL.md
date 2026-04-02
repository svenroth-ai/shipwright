---
name: shipwright-plan
description: Creates detailed implementation plans from spec files via research, interview, external LLM review, and TDD approach. Generates section-based plans for /shipwright-build. Use when you have a spec.md from /shipwright-project.
license: MIT
compatibility: Requires uv (Python 3.11+), git repository recommended. Optional: Gemini API key + OpenAI API key for external review.
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
  - Optional: GEMINI_API_KEY + OPENAI_API_KEY for external review
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

### C. Discover Plugin Root

The SessionStart hook injects `SHIPWRIGHT_PLUGIN_ROOT=<path>` into your context.

**If `SHIPWRIGHT_PLUGIN_ROOT` is in your context**, use it directly as `plugin_root`.

**Only if NOT in context** (hook didn't run), fall back to search:
```bash
find "$(pwd)" -name "setup-planning-session.py" -path "*/shipwright-plan/scripts/checks/*" -type f 2>/dev/null | head -1
```
If not found: `find ~ -name "setup-planning-session.py" -path "*/shipwright-plan/scripts/checks/*" -type f 2>/dev/null | head -1`

The plugin_root is the directory two levels up from `scripts/checks/`.

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

### F. Print Session Report

```
================================================================================
SESSION REPORT
================================================================================
Mode:              {new | resume}
Spec:              {spec_file}
Planning dir:      {planning_dir}
External review:   {enabled | disabled (no API keys)}
E2E test plan:     {enabled | disabled}
{Resume from:      Step {N} (if resuming)}
================================================================================
```

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
uv run {plugin_root}/../../shared/scripts/tools/write_decision_log.py \
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

## Step 5: External LLM Review (Optional)

See [external-review.md](references/external-review.md) for protocol.

**Goal:** Get plan reviewed by Gemini and OpenAI for blind spots.

**Prerequisite:** External review enabled in config AND API keys available.

Run the review script:
```bash
uv run --project {plugin_root} {plugin_root}/scripts/llm_clients/review.py \
  --plan-file "{planning_dir}/plan.md" \
  --spec-file "{spec_file}" \
  --plugin-root "{plugin_root}"
```

This runs Gemini and OpenAI reviews **in parallel** via ThreadPoolExecutor.

**If no API keys:** Skip gracefully with a note in the plan.

**If review returns feedback:**
1. Present feedback to user
2. Integrate valid suggestions into plan
3. Mark feedback as addressed

**Write review decisions to decision_log.md:**

After processing review feedback, log each accepted or rejected finding as a decision:

```bash
uv run {plugin_root}/../../shared/scripts/tools/write_decision_log.py \
  --section "External Review — {split_name}" \
  --commit "n/a" \
  --context "External LLM review finding: {finding summary}" \
  --decision "{accepted: what changed | rejected: why not}" \
  --consequences "{impact on plan}" \
  --rejected "{if accepted: original approach | if rejected: the suggestion itself}"
```

This ensures review-driven decisions (e.g., "add JWT custom claims for RLS", "use idempotent migrations") are visible in the decision log before build starts.

---

## Step 6: Section Splitting

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

**Only runs if `e2e_test_plan.enabled` is true in config.**

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
```bash
# Mark plan phase complete (triggers compliance update automatically)
uv run {plugin_root}/../../plugins/shipwright-run/scripts/lib/orchestrator.py \
  update-step --project-root "$(pwd)" --step plan --status complete

# Update delivery dashboard
uv run {shared_root}/scripts/tools/update_build_dashboard.py \
  --project-root "$(pwd)" --phase plan --detail "{N} sections for {split_name}" \
  --session-id "{SHIPWRIGHT_SESSION_ID}"
```
Where `{shared_root}` = `{plugin_root}/../../shared`.

**Print Summary:**
```
================================================================================
SHIPWRIGHT-PLAN COMPLETE
================================================================================
Plan:         {planning_dir}/plan.md
Sections:     {N} sections generated
External:     {reviewed by Gemini + OpenAI | skipped}
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
```
Note: External LLM review skipped.
  - GEMINI_API_KEY: {set | missing}
  - OPENAI_API_KEY: {set | missing}

The plan was created without external review.
You can add API keys and re-run to get external feedback.
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
