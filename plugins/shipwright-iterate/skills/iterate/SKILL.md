---
name: shipwright-iterate
description: "Lightweight SDLC for ongoing changes in completed Shipwright projects.\nTRIGGER when: user asks to add a feature, fix a bug, change behavior, refactor, update, modify, or improve code in a project that has shipwright_run_config.json. Also when user describes a bug report, enhancement request, or any code-level change.\nDO NOT TRIGGER when: user asks about project setup (/shipwright-project), planning (/shipwright-plan), initial build (/shipwright-build), deployment (/shipwright-deploy), or non-code tasks like documentation questions."
license: MIT
compatibility: Requires uv (Python 3.11+), git repository required, completed Shipwright project
---

# Shipwright Iterate Skill

Lightweight change lifecycle for completed Shipwright projects.
Detects intent (feature, change, bug), runs a lean process, keeps specs and tests in sync.

> **How it gets invoked:**
> 1. Directly via `/shipwright-iterate` (explicit)
> 2. Via UserPromptSubmit hook context (automatic — `suggest_iterate.py` detects code-change intent
>    and injects "[Shipwright] Detected: ..." context into the prompt)

---

## CRITICAL: First Actions

**Governing rules:** Read and follow `shared/constitution.md` (ALWAYS / ASK FIRST / NEVER boundaries).

**BEFORE using any other tools**, do these in order:

### A. Print Intro Banner

```
================================================================================
SHIPWRIGHT-ITERATE: Lightweight Change Lifecycle
================================================================================
Keeps specs, tests, and ADRs in sync for ongoing changes.

Usage: /shipwright-iterate --type feature|change|bug "description"
   or: Auto-detected from your prompt (via hook context)

Paths:
  FEATURE  → spec update → [design] → build → test → commit
  CHANGE   → spec update → build → test → commit
  BUG      → reproduce → fix → test → commit

All paths end with: spec sync + ADR + conventional commit
================================================================================
```

### B. Validate Project

1. Verify `shipwright_run_config.json` exists in the project root
2. Verify `status` is `"complete"` (iterate is for post-pipeline changes)
3. If not a completed Shipwright project, print:
```
================================================================================
SHIPWRIGHT-ITERATE: Completed Project Required
================================================================================

This skill is for changes to completed Shipwright projects.
The project must have status "complete" in shipwright_run_config.json.

For initial builds, use: /shipwright-run
================================================================================
```
**Stop and wait.**

### C. Determine Intent Type

**Priority order for type detection:**

1. **Explicit flag:** `--type feature|change|bug` from invocation
2. **Hook context:** Parse `[Shipwright] Detected: FEATURE|CHANGE|BUG` from additionalContext
3. **Auto-classify:** Run the classifier:
```bash
uv run {plugin_root}/scripts/lib/classify_intent.py \
  --message "{user_message}" \
  --sync-config "{project_root}/shipwright_sync_config.json"
```
4. **Ask user:** If confidence < 0.7 or type is "none", ask:
   > What type of change is this?
   > - **Feature** — new functionality
   > - **Change** — modify existing behavior
   > - **Bug** — fix something broken

Parse the JSON output. Use `type` and `affected_frs` for the workflow.

### D. Print Session Report

```
================================================================================
SESSION REPORT
================================================================================
Type:           {FEATURE | CHANGE | BUG}
Description:    {summary from classifier or user message}
Affected FRs:   {FR-01.08, FR-01.09 | TBD}
Branch:         {current branch or new iterate branch}
================================================================================
```

---

## Context Loading (Progressive Disclosure)

### Layer 1 — Always Load

These files provide essential context. Read them before starting work:

1. `shipwright_run_config.json` — project metadata, profile, completed sections
2. `CLAUDE.md` — project conventions, stack, commands
3. `agent_docs/decision_log.md` — past architectural decisions
4. `shipwright_sync_config.json` — file-to-FR mappings (if exists)

### Layer 2 — Load On-Demand

Read these only when the change touches their domain:

- `planning/*/spec.md` — only the spec for affected FRs
- `planning/*/sections/*.md` — only the section files for affected areas
- `designs/visual-guidelines.md` — only for UI changes
- `designs/screens/*.html` — only for UI changes requiring mockup reference
- `agent_docs/architecture.md` — only for structural changes
- `supabase/migrations/` — only for database changes

---

## Path A: FEATURE (new functionality)

### Step 1: Spec Update

1. Identify which spec file(s) cover the affected area (from sync config or Layer 2)
2. Read the relevant spec section
3. **Append** a new FR entry (or sub-entry) to the appropriate spec section:
   - FR ID follows the existing numbering scheme
   - Acceptance criteria defined
   - Test strategy outlined
4. If `shipwright_sync_config.json` exists, add a mapping for the new files

### Step 2: Design (conditional)

**Skip if:** The feature has no UI component, or the project has no `designs/` directory.

**If UI feature:**
1. Read `designs/visual-guidelines.md` for brand consistency
2. Describe what the new UI should look like (layout, components, interactions)
3. Note: Full mockup generation is out of scope for iterate — text description is sufficient
4. Reference existing mockups if the feature extends an existing screen

### Step 3: Build

1. Create a feature branch: `iterate/{short-description}`
2. **Write tests first** (TDD red phase):
   - Unit tests for new logic
   - Integration tests if touching existing code
3. **Implement** until tests pass (green phase)
4. Run full test suite to verify no regressions:
```bash
npx vitest run
npx tsc --noEmit
```

### Step 4: Test & Verify

1. Run the complete test suite:
```bash
npx vitest run
npx tsc --noEmit
```
2. If E2E tests exist and the change affects UI:
```bash
npx playwright test
```
3. **If tests fail:** Enter fix loop (max 3 attempts):
   a. Read error output, identify root cause
   b. State hypothesis before fixing
   c. Apply targeted fix
   d. Re-run failing tests
   e. If same root cause repeats, change approach
   f. After 3 failures, escalate to user

### Step 5: Finalize

Go to **Finalization** below.

---

## Path B: CHANGE (modify existing behavior)

### Step 1: Spec Update

1. Identify affected FRs from sync config or by reading the relevant spec
2. Read the current spec section for the affected area
3. **Update** the existing FR entry:
   - Modify acceptance criteria to reflect the change
   - Update test strategy if needed
4. Update `shipwright_sync_config.json` mappings if file paths changed

### Step 2: Build

1. Create a feature branch: `iterate/{short-description}`
2. **Update existing tests** to reflect new expected behavior
3. **Implement** the change
4. Run tests to verify:
```bash
npx vitest run
npx tsc --noEmit
```

### Step 3: Test & Verify

Same as Feature Path Step 4 above.

### Step 4: Finalize

Go to **Finalization** below.

---

## Path C: BUG (fix something broken)

### Step 1: Reproduce

1. Understand the reported bug from the user's description
2. **Write a failing test** that reproduces the bug:
   - The test should fail with the current code
   - The test should pass once the bug is fixed
3. Run the test to confirm it fails:
```bash
npx vitest run --reporter=verbose {test_file}
```

### Step 2: Fix

1. Create a feature branch: `iterate/fix-{short-description}`
2. **Fix the bug** — targeted change, minimal scope
3. Run the reproducing test to verify it passes:
```bash
npx vitest run --reporter=verbose {test_file}
```

### Step 3: Test & Verify

1. Run full test suite to verify no regressions:
```bash
npx vitest run
npx tsc --noEmit
```
2. If E2E tests exist and bug was UI-related:
```bash
npx playwright test
```
3. Follow the same fix loop as Feature Path Step 4 if tests fail.

### Step 4: Finalize

Go to **Finalization** below.

---

## Finalization (all paths)

### F1: Drift Check

Run artifact sync to verify specs match code:

```bash
uv run {shared_root}/scripts/artifact_sync.py \
  --project-root "{project_root}" --ref "HEAD~1..HEAD"
```

If drift detected, review the affected mappings and update specs as needed.

### F2: Decision Log (ADR)

Log the change in `agent_docs/decision_log.md`:

```bash
uv run {shared_root}/scripts/tools/write_decision_log.py \
  --section "Iterate — {type}: {short_description}" \
  --commit "$(git rev-parse HEAD)" \
  --title "{short title}" \
  --context "{why this change was needed}" \
  --decision "{what was done}" \
  --consequences "{impact}" \
  --rationale "{reasoning}" \
  --rejected "{alternatives considered}" \
  --project-root "{project_root}"
```

### F3: Commit (Conventional Commits)

Stage and commit with the appropriate type:

- **Feature:** `feat({scope}): {description}`
- **Change:** `refactor({scope}): {description}` or `feat({scope}): {description}` if user-facing
- **Bug:** `fix({scope}): {description}`

```bash
git add -A
git commit -m "<type>(<scope>): <description>

<body>

Co-Authored-By: Claude <noreply@anthropic.com>"
```

### F3.5: Record Event

After the commit succeeds, record the work event in the unified event log. Use the EXACT values from this iteration — do not use placeholder braces. Pick one intent value: `feature`, `change`, or `bug`. Parse the vitest summary line (`Tests: 47 passed, 47 total`) for the test counts. Omit `--new-frs` and `--spec-updated` if not applicable. The `--deduplicate-by-commit` flag prevents duplicate events if this step is retried.

```bash
# Example for a feature iteration:
uv run {shared_root}/scripts/tools/record_event.py \
  --project-root "{project_root}" \
  --type work_completed --source iterate \
  --intent feature \
  --description "Add course filtering by category" \
  --commit "$(git rev-parse HEAD)" \
  --affected-frs "FR-02.08" \
  --new-frs "FR-02.08" \
  --spec-updated "planning/02-course-platform/spec.md" \
  --tests-new 3 --tests-passed 47 --tests-total 47 \
  --e2e-run false \
  --adr-id "ADR-055" \
  --deduplicate-by-commit
```

### F3.7: Update Compliance

Trigger incremental compliance report regeneration:

```bash
uv run {shared_root}/../../plugins/shipwright-compliance/scripts/tools/update_compliance.py \
  --project-root "{project_root}" --phase iterate
```

### F4: Print Summary

```
================================================================================
SHIPWRIGHT-ITERATE COMPLETE
================================================================================
Type:       {FEATURE | CHANGE | BUG}
Branch:     iterate/{short-description}
Commit:     {commit_hash}
Event:      {event_id from F3.5 output}
Tests:      {N} passing
Specs:      {updated | no changes needed}
ADR:        Logged in decision_log.md

Next steps:
  1. Review: git diff main..iterate/{short-description}
  2. Merge:  git checkout main && git merge iterate/{short-description}
  3. Push:   git push origin main
================================================================================
```

---

## Error Handling

### Test Failures
1. **Root cause investigation** — read error output, identify failing component
2. **Pattern analysis** — same root cause as last attempt? Change approach
3. **Hypothesis** — state what you'll fix and why before changing code
4. **Fix and verify** — targeted fix, then re-run tests
5. If stuck after 3 attempts: escalate to user

### Pre-commit Hook Failures
- Linting failures: auto-fix and re-commit
- Type errors: fix and re-commit
- Never bypass hooks with `--no-verify`

### Missing Sync Config
If `shipwright_sync_config.json` does not exist:
- Skip FR mapping (affected_frs = TBD)
- Skip drift check in finalization
- Log a note: "Consider creating shipwright_sync_config.json for drift detection"
