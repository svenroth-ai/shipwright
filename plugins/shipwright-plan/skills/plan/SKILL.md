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

**Governing rules:** Read and follow `shared/constitution.md` (ALWAYS /
ASK FIRST / NEVER boundaries).

**BEFORE using any other tools**, run [first-actions.md](references/first-actions.md)
in order:

- **A.** Print Intro Banner
- **B.** Validate Input — stop if `@spec.md` missing/invalid
- **C.** Detect Invocation Mode — resolve via `get_phase_context.py
  --phase-task-id "{phaseTaskId}" --phase plan`; store `mode` as `invocation_mode`
  (`pipeline`|`standalone`|`error`→STOP). Token is authority, never re-derive from run state. [first-actions](references/first-actions.md).
- **C2.** Load Project Context (MANDATORY): `CLAUDE.md`,
  `.shipwright/agent_docs/conventions.md`, `decision_log.md`,
  `architecture.md`, and `git log --oneline -10`. WARN on missing
  files; never silently skip.
- **D.** Discover Plugin Root — prefer `SHIPWRIGHT_PLUGIN_ROOT` env
  injected by the SessionStart hook; otherwise `find` for
  `setup-planning-session.py`.
- **D2.** Run Setup Script
  (`{plugin_root}/scripts/checks/setup-planning-session.py`).
  Parse JSON: `success == true` → proceed; `mode == "resume"` →
  jump to `resume_from_step`; `success == false` → stop.
- **E.** Load Config (`{plugin_root}/config.json` plus per-session
  overrides under `{planning_dir}/shipwright_plan_config.json`).
  Write the **early in-progress plan config** via
  `write-plan-config.py --status in_progress` so a mid-flight
  handoff still works.
- **F.** Print Session Report (mode / spec / planning_dir /
  external_review status / E2E flag / resume-from).

Full text — banners, scripts, every CLI arg — in
[first-actions.md](references/first-actions.md). The agent reads that
on-demand when it lands here.

---

## Step 0: Phase Session Context Recovery

See [step-0-context-recovery.md](references/step-0-context-recovery.md).

If the orchestrator handed you a `phaseTaskId` (you were dispatched as a
phase-runner subagent by `/shipwright-run`), run
`shared/scripts/tools/get_phase_context.py --phase-task-id <id>` as your very
first action, then read every artifact in the returned `skill_artifacts_to_read`
list before proceeding. No `phaseTaskId` → standalone invocation, continue
with Step 1.

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
Adaptive questions on architecture / data model / UX; clarify
ambiguities; identify risks.

**Checkpoint:** Write `{planning_dir}/shipwright_plan_interview.md`
with full transcript.

**Write interview decisions to decision_log.md** for every
architecture/design decision that goes beyond what the profile or
project interview already decided (e.g. ORM vs raw SQL, component
library variants, caching, API patterns):

```bash
uv run "{plugin_root}/../../shared/scripts/tools/write_decision_log.py" \
  --section "Plan Interview — {split_name}" --commit "n/a" \
  --context "{why}" --decision "{what}" \
  --consequences "{impact}" --rejected "{alternatives}"
```

---

## Step 3: Context Check

See [context-check.md](references/context-check.md) for detailed guidance.

**Goal:** Before writing the plan, assess if context window is getting large.

```bash
uv run --project {plugin_root} {plugin_root}/scripts/checks/check-context-decision.py
```

If context is large: summarize research findings first; or write a brief
outline for user approval before continuing.

---

## Step 4: Plan Writing

See [plan-writing.md](references/plan-writing.md) and
[tdd-approach.md](references/tdd-approach.md) for guidance.

**Goal:** Write the implementation plan as prose with TDD approach.

**Plan structure:**
- Overview of approach
- Section breakdown with SECTION_MANIFEST
- For each section: goals, implementation steps, test strategy
- Cross-cutting concerns

See [section-index.md](references/section-index.md) for the
SECTION_MANIFEST format.

**Checkpoint:** Write `{planning_dir}/plan.md` with SECTION_MANIFEST block.

---

## Step 5: External LLM Review (Default + Fallback)

See [step-5-external-review.md](references/step-5-external-review.md)
for the full branch logic, and [external-review.md](references/external-review.md)
for the underlying protocol.

**This step is NOT optional.** One of three branches must run to
completion, and the marker file
`{planning_dir}/external_review_state.json` must be written. Step 6
is gated on that marker.

Read `external_review_status` from the session report (First Actions
> F). Branch on its value:

- **Branch A — `available`:** run
  `shared/scripts/tools/external_review.py --mode plan ...` (Gemini +
  OpenAI in parallel), integrate findings, log every finding to
  `decision_log.md`, then go to Step 5b.
- **Branch B — `missing_keys`:** STOP. Ask user verbatim (Option 1:
  add key + retry → Branch A; Option 2: skip → Self-Review Fallback).
  Do NOT proceed until the user chooses.
- **Branch C — `user_disabled`:** print the disabled notice, run
  the Self-Review Fallback sub-block ("2x denken" — 5-item checklist:
  architectural soundness / section boundaries / TDD coverage / risk
  hotspots / assumptions).

After exactly one branch completes, **Step 5b** writes the marker:

```bash
uv run --project {plugin_root} {shared_root}/scripts/checks/mark-review-state.py \
  --planning-dir "{planning_dir}" \
  --status "{completed | skipped_user_opt_out | skipped_config_disabled}" \
  --provider "{openrouter | gemini | openai | null}" \
  --findings-count {N} \
  --reason "{optional reason for skip}"
```

**Checkpoint:** `{planning_dir}/external_review_state.json` exists.

---

## Step 6: Section Splitting

**Gate:** Read `{planning_dir}/external_review_state.json`. If missing,
STOP — Step 5 was not completed. Return to Step 5 and pick the
appropriate branch. If present, proceed.

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

Each section file is written **by the `shipwright-plan:section-writer` subagent
itself** — it has a Write tool and persists `{planning_dir}/sections/{NN-name}.md`
directly (SS4). The `write-section-on-stop.py` SubagentStop hook is a
**non-blocking fallback** only (no-op when the file exists; best-effort salvage
from the transcript otherwise; never blocks). Step 7 (`check-sections.py`) is the
gate. See [section-splitting.md](references/section-splitting.md) for details.

**Checkpoint:** All section files exist in `{planning_dir}/sections/`.

---

## Step 7: Section Validation

```bash
uv run --project {plugin_root} {plugin_root}/scripts/checks/check-sections.py \
  --planning-dir "{planning_dir}"
```

Verify all sections declared in SECTION_MANIFEST have corresponding files.

---

## Step 8: E2E Test Plan (Shipwright Enhancement — Optional)

See [e2e-test-plan.md](references/e2e-test-plan.md) for guidance.

**Runs if** `e2e_test_plan.enabled` is true in config, OR if no config
exists and the project has a UI (`.shipwright/designs/screens/`
contains HTML mockups, or `component_library` is set in profile —
default enabled for UI projects).

**Goal:** Generate a Playwright E2E test plan — user-facing flows
(login, CRUD, navigation), test scenarios with expected outcomes, POM
suggestions.

**Checkpoint:** Write `{planning_dir}/claude-plan-e2e.md`.

---

## Step 9: Completion

See [step-9-completion.md](references/step-9-completion.md) for the
full verification checklist and the C1+C2+C3+C4 + `phase_history`
canon block (Iterate 12.2 — C5 skipped by policy: plan is internal
decomposition, not user-facing).

**Verification gates (all must pass):**

1. plan.md exists with SECTION_MANIFEST
2. All declared sections have files
3. Interview transcript exists
4. E2E test plan exists (if enabled)
5. Section Quality Gate (description + ≥2 implementation steps + test strategy)
6. FR Coverage Check (every FR assigned to ≥1 section)
7. Dependency Order (sections after their dependencies in SECTION_MANIFEST)

**Phase complete:** set `SHIPWRIGHT_RUN_ID`, run
`write-plan-config.py --status complete`, fire `record_event.py`,
`update_build_dashboard.py`, `generate_session_handoff.py --canon-marker`,
`append_phase_history.py`, then
`orchestrator.py update-step --step plan --status complete`. See
[step-9-completion.md](references/step-9-completion.md) for the exact
commands.

---

## Error Handling

See [error-handling.md](references/error-handling.md) for the full
recovery procedures:

- **Missing API Keys:** handled interactively in Step 5 Branch B
  (Option 1 add+retry / Option 2 self-review). Never silently skipped.
- **Section Writer Failure:** log → retry directly without subagent →
  mark incomplete and continue.
- **Context Window Pressure:** save → suggest `/clear` → resume from
  any step.

---

## Reference Documents

Per-step refs: [first-actions.md](references/first-actions.md),
[step-0-context-recovery.md](references/step-0-context-recovery.md),
[step-5-external-review.md](references/step-5-external-review.md),
[step-9-completion.md](references/step-9-completion.md),
[error-handling.md](references/error-handling.md).

Topical refs: [research-protocol.md](references/research-protocol.md),
[interview-protocol.md](references/interview-protocol.md),
[context-check.md](references/context-check.md),
[plan-writing.md](references/plan-writing.md),
[tdd-approach.md](references/tdd-approach.md),
[section-index.md](references/section-index.md),
[section-splitting.md](references/section-splitting.md),
[external-review.md](references/external-review.md),
[e2e-test-plan.md](references/e2e-test-plan.md).
