---
name: shipwright-project
description: "Decomposes project requirements into well-scoped planning units for /shipwright-plan. Generates CLAUDE.md and .shipwright/agent_docs for the target project.\nTRIGGER when: user wants to start a new project, define requirements, create a project spec, decompose a project into components, scaffold a new application, set up project structure, analyze requirements, or extend an existing project with new features that need full planning.\nDO NOT TRIGGER when: user asks to implement code (/shipwright-build), run tests (/shipwright-test), fix a bug or make a small change (/shipwright-iterate), deploy (/shipwright-deploy), generate a changelog (/shipwright-changelog), plan implementation details for an existing spec (/shipwright-plan), or design UI mockups (/shipwright-design)."
license: MIT
compatibility: Requires uv (Python 3.11+), git repository recommended
---

# Shipwright Project Skill

Decomposes project requirements into well-scoped components for /shipwright-plan.
Enhanced fork of deep-project with profile-aware decomposition and project scaffolding.

This Kern is a thin orchestrator — section headers + cross-references to
`references/*.md`. Read the references on-demand when the corresponding
step fires. The agent reads Kern fully at startup; references are loaded
when their step is reached.

---

## CRITICAL: First Actions

**Governing rules:** Read and follow `shared/constitution.md` (ALWAYS /
ASK FIRST / NEVER boundaries).

**BEFORE using any other tools**, complete the First Actions checklist
in [references/first-actions.md](references/first-actions.md):

- **A.** Print intro banner
- **A.1** Startup check (first turn only — `shipwright_run_config.json`
  presence; if missing, AskUserQuestion + END TURN)
- **A.2** Startup check next turn (handle Full Pipeline vs Standalone
  Spec answer)
- **B.** Detect scope (Full Application vs Extension)
- **C.** Detect input mode (File / Inline / Chat)
- **D.** Detect invocation mode (pipeline vs standalone)
- **E.** Discover plugin root + run setup script
- **F.** Handle session state (new vs resume)
- **G.** Print session report

The reference file is authoritative for the exact prompts, banner text,
shell invocations, and resume-step mapping. Do not paraphrase or
condense — copy verbatim from the reference into your output where
required.

### Single-Session Gate Discipline

When this phase runs as a phase-runner subagent under the **single-session
pipeline** (`shipwright_run_config.json` `mode: "single_session"`), interactive
`AskUserQuestion` gates — incl. **A.1** and **Step 4** — follow a per-gate policy.
Resolve each before stopping:

```bash
uv run "${SHIPWRIGHT_PLUGIN_ROOT}/../../shared/scripts/tools/resolve_gate_policy.py" \
  --phase project --list --project-root .
```

Apply the `effective_policy`: `auto-default` → proceed with the `default_answer`
(no END-TURN; e.g. the interview is answered from the seed, the split manifest is
auto-approved); `orchestrator-approve` / `hard-stop` → STILL STOP and hand back to
the orchestrator (never auto-answer — e.g. a missing Supabase secret). Under
`multi_session`/standalone every gate is `interactive` (unchanged). Full contract:
`shared/prompts/single-session-gate-discipline.md`.

---

## Step 0: Phase Session Context Recovery

See [references/step-0-context-recovery.md](references/step-0-context-recovery.md).

If `=== SHIPWRIGHT-PIPELINE-CONTEXT ===` is in your context, you are part
of an active `/shipwright-run` pipeline — parse `phaseTaskId` and run
`get_phase_context.py` BEFORE Step 1. Otherwise (standalone), continue
with Step 1.

---

## Step 1: Interview

See [references/step-1-interview.md](references/step-1-interview.md) for
the full step. Detailed interview guidance is in
[references/interview-protocol.md](references/interview-protocol.md).

**Goal:** Surface the user's mental model of the project and combine it
with Claude's intelligence.

**Assumptions-first (before the first clarifying question):** list your
inferred assumptions explicitly — web-app vs CLI, stack, persistence, auth
model — and ask the user to correct them. See the "Surface Inferred
Assumptions First" pre-phase in
[interview-protocol.md](references/interview-protocol.md).

**Context to read** depends on input mode (File / Inline / Chat). For
Extension scope, read ALL existing project context (CLAUDE.md,
`.shipwright/agent_docs/*`, all `.shipwright/planning/*/spec.md`).

**Interview depth** ranges Light (1-3) for Extensions to Deep (8-15)
for Chat-mode Full Applications. **One AskUserQuestion per question.**

**Checkpoints:**
1. Write `{planning_dir}/shipwright_project_interview.md` (transcript)
2. **Inline/Chat only:** also write `{planning_dir}/requirements.md`

---

## Step 2: Split Analysis

See [references/split-heuristics.md](references/split-heuristics.md) for
evaluation criteria.

**Goal:** Determine if project benefits from multiple splits or is a
single coherent unit.

**Context to read:**
- `{initial_file}` - The original requirements
- `{planning_dir}/shipwright_project_interview.md` - Interview transcript

---

## Step 3: Dependency Discovery & project-manifest.md

See [references/project-manifest.md](references/project-manifest.md)
for manifest format.

**Goal:** Summarize splits, map relationships and write the project
manifest.

**Checkpoint:** Write `{planning_dir}/project-manifest.md` with Claude's
proposal.

---

## Step 4: User Confirmation

See [references/step-4-confirmation.md](references/step-4-confirmation.md).

**Goal:** Get user approval on split structure.

Present the manifest and use AskUserQuestion to get the user's feedback.
If changes requested, update `project-manifest.md` directly and
re-present. On approval, proceed to Step 5.

---

## Step 5: Create Directories

See [references/step-5-create-dirs.md](references/step-5-create-dirs.md).

**Goal:** Create split directories from the approved manifest.

```bash
uv run "{plugin_root}/scripts/checks/create-split-dirs.py" --planning-dir "{planning_dir}"
```

**Checkpoint:** Directory existence. Resume from Step 6 if directories
exist.

---

## Step 6: Spec Generation

See [references/step-6-spec-gen.md](references/step-6-spec-gen.md).
Detailed file formats in
[references/spec-generation.md](references/spec-generation.md).

**Goal:** Write spec files for each split directory.

**Checkpoint:** Spec file existence.

---

## Step 7: Project Scaffolding (NEW — Shipwright Enhancement)

See [references/step-7-scaffolding.md](references/step-7-scaffolding.md).
Detailed CLAUDE.md + .shipwright/agent_docs generation in
[references/project-scaffolding.md](references/project-scaffolding.md).

**Goal:** Generate CLAUDE.md and `.shipwright/agent_docs/` for the
target project.

**This step only runs for Full Application scope.** Extensions already
have these files.

Key sub-flows (see reference for the verbatim shell commands and
templates):

1. **Profile detection** — match interview against
   `{plugin_root}/../../shared/profiles/` JSONs; supabase-nextjs is the
   primary supported profile.
2. **Generate** CLAUDE.md, `architecture.md`, `decision_log.md`,
   `conventions.md`, and `.claude/rules/*.md`.
3. **Phase-router hook** — `suggest_iterate` is registered in
   `shipwright-iterate`; no project-level install. Cleanup of legacy
   `.claude/settings.json` `UserPromptSubmit` entries is documented in
   the reference.
4. **Write config** via `write-project-config.py`.
5. **Write interview decisions** to `decision_log.md` via the shared
   `write_decision_log.py` tool — once per project-specific decision.
6. **Supabase setup** (supabase-nextjs profile only) — `supabase init`,
   `supabase link --project-ref`, verify `.supabase/` exists.
7. **GitHub Repo Hygiene** — enable `delete_branch_on_merge=true` if a
   GitHub remote exists.

**Checkpoint:** CLAUDE.md existence + `supabase/config.toml` existence
(supabase-nextjs only).

---

## Step 8: Completion

See [references/step-8-completion.md](references/step-8-completion.md)
for the full verification list, the C1/C2/C3/C4/C5 + phase_history
canon, and the final summary banner.

**Verification (all must pass before "phase complete"):**

1. All declared splits have spec.md files
2. project-manifest.md exists and lists all splits with execution order
3. CLAUDE.md exists (Full Application only)
4. `.shipwright/agent_docs/` directory exists with all 5 files (Full
   Application only)
5. **Spec Completeness Gate** — Scope + FRs + NFRs in each spec.md
6. **Manifest-Spec Consistency** — bijection between manifest and
   spec.md files

**Phase complete — update pipeline state** by running the
C1/C2/C3/C5 + phase_history block from
[references/step-8-completion.md](references/step-8-completion.md), then
call the orchestrator update-step to mark the project phase complete.

---

## Error Handling

See [references/error-handling.md](references/error-handling.md) for
the invalid-input-file and session-conflict prompts.

---

## Reference Documents

- [first-actions.md](references/first-actions.md) — First Actions (A..G) verbatim
- [step-0-context-recovery.md](references/step-0-context-recovery.md) — Phase Session Context Recovery
- [step-1-interview.md](references/step-1-interview.md) — Interview step (links to interview-protocol.md)
- [step-4-confirmation.md](references/step-4-confirmation.md) — User Confirmation
- [step-5-create-dirs.md](references/step-5-create-dirs.md) — Create Directories
- [step-6-spec-gen.md](references/step-6-spec-gen.md) — Spec Generation (links to spec-generation.md)
- [step-7-scaffolding.md](references/step-7-scaffolding.md) — Project Scaffolding (links to project-scaffolding.md)
- [step-8-completion.md](references/step-8-completion.md) — Completion + canon block + summary
- [error-handling.md](references/error-handling.md) — Error prompts
- [interview-protocol.md](references/interview-protocol.md) — Interview guidance and question strategies
- [split-heuristics.md](references/split-heuristics.md) — How to evaluate split quality
- [project-manifest.md](references/project-manifest.md) — Manifest format with SPLIT_MANIFEST block
- [spec-generation.md](references/spec-generation.md) — Spec file templates
- [project-scaffolding.md](references/project-scaffolding.md) — CLAUDE.md + .shipwright/agent_docs generation
