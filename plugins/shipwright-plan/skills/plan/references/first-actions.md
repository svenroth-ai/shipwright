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

**The `phaseTaskId` the orchestrator hands you at dispatch is the authority** — NOT any
state field inside `shipwright_run_config.json`. The pipeline's v1 state fields are no
longer advanced, so keying on them made every driven phase past the first misclassify
itself as standalone; the rationale is in `shared/scripts/lib/phase_invocation_mode.py`.
**Never re-derive the mode yourself.** Ask the resolver:

```bash
uv run "{shared_root}/scripts/tools/get_phase_context.py" \
  --phase-task-id "{phaseTaskId}" --phase plan --project-root "{project_root}"
```

Omit `--phase-task-id` if you were not handed one. Set `invocation_mode` from the returned
`mode`, which is exactly one of:

- **`pipeline`** — you were dispatched. Enforce gates, and do the phase's real work.
  **Do NOT call `orchestrator.py update-step`** (nor any other run-state write): in a
  driven run `single-session-apply` owns phase completion — it records your status when
  it applies your result. See `plugins/shipwright-run/skills/run/SKILL.md`. (`update-step`
  is inert in a driven run anyway, but do not rely on that.) Do NOT mark artifacts standalone.
- **`standalone`** — no token, so this is a hand-invoked run:
  - Skip pipeline state updates (no `orchestrator.py update-step` calls)
  - Skip upstream completion checks
  - Still produce all artifacts (`shipwright_plan_config.json`, section files)
  - **Mark artifacts**: when writing `shipwright_plan_config.json`, add `"mode": "standalone"` at the top level.
  - Print: `"Running in standalone mode — pipeline state will not be updated."`
  - If `requires_out_of_sequence_warning` is `true`, a driven run is LIVE at
    `active_phases`. Warn that running `/shipwright-plan` out-of-band may collide with it,
    and **ask the user before continuing** (gate `plan.out-of-sequence-continue`).
- **`error`** (exit code 2) — you were dispatched but the token does not resolve (stale,
  terminal, wrong phase, or an unreadable config). **STOP.** Do NOT continue as
  standalone: that is precisely what stamps a driven run's artifacts `"mode": "standalone"`
  and deadlocks the pipeline. Surface it to the orchestrator as an `ok: false` result.

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
