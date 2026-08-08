---
name: shipwright-plan
description: "Creates detailed implementation plans from spec files via research, interview, external LLM review, and TDD approach. Generates section-based plans for /shipwright-build.\nTRIGGER when: user wants to plan implementation, create an implementation plan, break down a spec into sections, plan how to build something, create a technical design, generate build sections, or plan test strategy for a spec.\nDO NOT TRIGGER when: user asks to implement or write code (/shipwright-build), run tests (/shipwright-test), fix a bug or make a small change (/shipwright-iterate), deploy (/shipwright-deploy), define requirements (/shipwright-project), or design UI mockups (/shipwright-design)."
license: MIT
compatibility: Requires uv (Python 3.11+), git repository recommended. Recommended: OPENROUTER_API_KEY for DeepSeek + OpenAI review; OPENAI_API_KEY can run the GPT arm only. An internal review (model resolved via the `plan_review` role — inherit unless a project configures it) always runs first; if external keys are missing, the skill asks whether to skip and rely on that internal review.
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
Read the spec thoroughly; explore an existing codebase's structure and
patterns, or review comparable ones for a new project; web-search unfamiliar
technologies.

**Checkpoint:** Mental model formed. No file written — research informs all subsequent steps.

---

## Step 2: Interview

See [interview-protocol.md](references/interview-protocol.md) for detailed guidance.

**Goal:** Surface design decisions, constraints and preferences — adaptive
questions on architecture / data model / UX; clarify ambiguities; find risks.

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

**Plan structure:** overview of approach; section breakdown with
SECTION_MANIFEST; per section goals, implementation steps and test strategy;
cross-cutting concerns. Manifest format — including how a section declares
what it presupposes — in [section-index.md](references/section-index.md).

**Checkpoint:** Write `{planning_dir}/plan.md` with SECTION_MANIFEST block.

---

## Step 5: External LLM Review (Default + Fallback)

Full branch logic: [step-5-external-review.md](references/step-5-external-review.md);
underlying protocol: [external-review.md](references/external-review.md).

**This step is NOT optional.** An internal review always runs first
(Step 5-int); then one of three branches must run to completion, and
`{planning_dir}/external_review_state.json` must be written. Step 6 is
gated on both.

**Step 5-int (always, first):** spawn `shipwright-plan:opus-plan-reviewer`
over `plan.md` + `spec.md`; triage every finding fix/disclose/decline
(reason required; scope-ratchet guard) — a declined/disclosed
`severity: high` finding STOPs and asks the user before Step 6, per
`gate_catalog.json`. Write `## Internal Plan Review` to `plan.md`
(`Ran: yes|no`; replace in place on retry), log to `decision_log.md`. No
marker of its own — on failure record `Ran: no` and continue to the branch
below; the **Pre-5b Checkpoint** decides whether the Self-Review Fallback
runs. Then read `external_review_status` from the session report (First
Actions > F) and branch on its value:

- **Branch A — `available`:** run `external_review.py --mode plan ...`
  (DeepSeek + OpenAI in parallel), integrate findings, log each to
  `decision_log.md`. Read `contradiction.requires_resolution` first — put any
  disagreement to the user, never proceed on the approving review alone. Then
  **Step 5a**: a second call, `--mode architecture` over a short brief
  *instead of* the plan, asking what no other pass asks — should this be
  built at all; `reject` STOPs before Step 6. Then the Pre-5b Checkpoint.
- **Branch B — `missing_keys`:** STOP. Ask user verbatim (Option 1: add key +
  retry → Branch A; Option 2: skip — Step 5-int's `Ran:` value decides the
  fallback, per the Pre-5b Checkpoint). Do NOT proceed until chosen.
- **Branch C — `user_disabled`:** print the disabled notice, then the
  Pre-5b Checkpoint.

After exactly one branch completes, the **Pre-5b Checkpoint** runs the
Self-Review Fallback if neither Step 5-int nor Branch A produced a completed
independent review, then **Step 5b** writes the marker with
`{shared_root}/scripts/checks/mark-review-state.py` — `--status`,
`--provider`, `--findings-count`, `--reason`, one
`--verdict {deepseek|openai}={verdict}` per reviewer,
`--contradiction-resolution` when they disagreed, and
`--self-review-fallback-ran` when the checkpoint ran it. Exact invocation:
[step-5-external-review.md](references/step-5-external-review.md).

**Checkpoint:** `{planning_dir}/external_review_state.json` exists and records
a state clear to proceed past — the same question the resume gate and
compliance `W5` ask, through one shared evaluator.

---

## Step 6: Section Splitting

**Gate — run it, don't eyeball it:**

```bash
uv run --project {plugin_root} {plugin_root}/scripts/checks/check-plan-gates.py \
  --planning-dir "{planning_dir}" --gate review
```

Non-zero exit = STOP. It fails when Step 5 left no marker, or the marker
records a reviewer disagreement nobody decided. Return to Step 5, pick the
branch or record the decision, then re-run. The resume gate and compliance
`W5` apply the same rule through the same function.

See [section-splitting.md](references/section-splitting.md) for protocol.

**Goal:** Split plan into self-contained section files for /shipwright-build:
parse SECTION_MANIFEST, generate section tasks, then per section spawn the
section-writer subagent or write it directly.

**Batch approach (recommended for 3+ sections):**
```bash
uv run --project {plugin_root} {plugin_root}/scripts/checks/generate-batch-tasks.py \
  --planning-dir "{planning_dir}"
```

Each section file is written **by the `shipwright-plan:section-writer` subagent
itself** (it has a Write tool); `write-section-on-stop.py` is a non-blocking
salvage fallback, and Step 7 is the gate. Every section needs a
`Requirements:` line, `## Overview`, ≥2 `## Implementation Steps` and
`## Tests First` — Step 9 fails without them.
Details: [section-splitting.md](references/section-splitting.md).

**Checkpoint:** All section files exist in `{planning_dir}/sections/`.

---

## Step 7: Section Validation

```bash
uv run --project {plugin_root} {plugin_root}/scripts/checks/check-sections.py \
  --planning-dir "{planning_dir}"
```

Verifies two things: every section declared in SECTION_MANIFEST has a file,
and the numbering agrees with the dependencies each section declares
(`03-api: 01-auth, 02-database`). A prerequisite numbered after the section
that needs it lands in `order_errors` and exits non-zero. Format:
[section-index.md](references/section-index.md).

---

## Step 8: E2E Test Plan (Shipwright Enhancement — Optional)

See [e2e-test-plan.md](references/e2e-test-plan.md) for guidance.

**Runs if** `e2e_test_plan.enabled` is true, OR no config exists and the
project has a UI (HTML mockups under `.shipwright/designs/screens/`, or
`component_library` set in the profile — default on for UI projects).

**Goal:** Generate a Playwright E2E test plan — user-facing flows (login,
CRUD, navigation), scenarios with expected outcomes, POM suggestions.

**Checkpoint:** Write `{planning_dir}/claude-plan-e2e.md`.

---

## Step 9: Completion

See [step-9-completion.md](references/step-9-completion.md) for the full procedure; after section validation and before completion, refresh planned paths via `uv run "{shared_root}/scripts/tools/area_catalog.py" seed-greenfield --project-root "$(pwd)" --source plan`. The
checklist and the C1+C2+C3+C4 + `phase_history` canon block (C5 skipped by
policy: plan is internal decomposition, not user-facing).

**Verification gates (all must pass).** Gates 5–8 are one command — run it:

```bash
uv run --project {plugin_root} {plugin_root}/scripts/checks/check-plan-gates.py \
  --planning-dir "{planning_dir}" --gate sections
```

1. plan.md exists with SECTION_MANIFEST
2. All declared sections have files
3. Interview transcript exists
4. E2E test plan exists (if enabled)
5. Section Quality (`## Overview` + ≥2 `## Implementation Steps` + `## Tests First`)
6. FR Coverage (every live FR named by ≥1 section's `Requirements:` line)
7. Section Trace (every section names ≥1 live FR — no work nobody asked for)
8. Dependency Order (every declared dependency numbered before its user)

Non-zero exit = STOP. `_validate_plan` re-runs 5–8, so skipping defers it.

**Phase complete:** set `SHIPWRIGHT_RUN_ID`, then run
`write-plan-config.py --status complete`, `record_event.py`,
`update_build_dashboard.py`, `generate_session_handoff.py --canon-marker`,
`append_phase_history.py`, `orchestrator.py update-step --step plan --status
complete` — exact commands in
[step-9-completion.md](references/step-9-completion.md).

---

## Error Handling

See [error-handling.md](references/error-handling.md) for the full recovery
procedures: missing API keys (Step 5 Branch B — never silently skipped),
section-writer failure (retry without the subagent, then mark incomplete),
and context-window pressure (save, `/clear`, resume from any step).

---

## Reference Documents

Per-step refs:
- [first-actions.md](references/first-actions.md)
- [step-0-context-recovery.md](references/step-0-context-recovery.md)
- [step-5-external-review.md](references/step-5-external-review.md)
- [step-9-completion.md](references/step-9-completion.md)
- [error-handling.md](references/error-handling.md)

Topical refs: [research-protocol.md](references/research-protocol.md), [interview-protocol.md](references/interview-protocol.md), [context-check.md](references/context-check.md), [plan-writing.md](references/plan-writing.md), [tdd-approach.md](references/tdd-approach.md), [section-index.md](references/section-index.md), [section-splitting.md](references/section-splitting.md), [external-review.md](references/external-review.md), [e2e-test-plan.md](references/e2e-test-plan.md).
