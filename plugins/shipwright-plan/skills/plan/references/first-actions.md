# First Actions (A–F)

Detailed expansion of the Kern `## CRITICAL: First Actions` checklist.
Read this when you start a `/shipwright-plan` invocation and need the
full procedure for steps A through F.

**Governing rules:** Read and follow `shared/constitution.md` (ALWAYS /
ASK FIRST / NEVER boundaries).

---

## A. Print Intro Banner

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

---

## B. Validate Input

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

---

## C. Detect Invocation Mode

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

Store the detected mode in a variable `invocation_mode` = `"pipeline"` | `"standalone"` for use in later steps.

---

## C2. Load Project Context (MANDATORY)

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

---

## D. Discover Plugin Root

The SessionStart hook injects `SHIPWRIGHT_PLUGIN_ROOT=<path>` into your context.

**If `SHIPWRIGHT_PLUGIN_ROOT` is in your context**, use it directly as `plugin_root`.

**Only if NOT in context** (hook didn't run), fall back to search:
```bash
find "$(pwd)" -name "setup-planning-session.py" -path "*/shipwright-plan/scripts/checks/*" -type f 2>/dev/null | head -1
```
If not found: `find ~ -name "setup-planning-session.py" -path "*/shipwright-plan/scripts/checks/*" -type f 2>/dev/null | head -1`

The plugin_root is the directory two levels up from `scripts/checks/`.

---

## D2. Run Setup Script

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

---

## E. Load Config

Read `{plugin_root}/config.json` for external review and E2E settings.

Check for session-specific overrides in `{planning_dir}/shipwright_plan_config.json`.

**Early config:** Write a minimal plan config for phase tracking (enables session handoff if user stops early):
```bash
uv run "{plugin_root}/scripts/checks/write-plan-config.py" \
  --project-root "$(pwd)" --status in_progress
```
This will be overwritten with the full config at Step 9 (completion).

---

## F. Print Session Report

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

## Single-Session Gate Discipline

When this phase runs as a phase-runner subagent under the **single-session
pipeline** (`shipwright_run_config.json` `mode: "single_session"`), interactive
`AskUserQuestion` gates follow a per-gate policy instead of always stopping.
Resolve each gate before you stop on it:

```bash
uv run "${SHIPWRIGHT_PLUGIN_ROOT}/../../shared/scripts/tools/resolve_gate_policy.py" \
  --phase plan --list --project-root .
```

Apply the printed `effective_policy`:

- `auto-default` → proceed with the `default_answer`, **no END-TURN**. (The
  interview is answered from loaded project context; a missing external-review key
  falls back to the mandatory self-review. Human plan-review is deferred to the
  orchestrator's cross-phase gate.)
- `orchestrator-approve` / `hard-stop` → **STILL STOP** and hand a gate-pending
  result back to the orchestrator; never auto-answer.
- `interactive` (any non-single-session run) → behave exactly as documented.

Full contract: `shared/prompts/single-session-gate-discipline.md`.
