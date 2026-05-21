---
name: shipwright-iterate
description: "Lightweight SDLC for ongoing changes in completed Shipwright projects.\nTRIGGER when: user asks to add a feature, fix a bug, change behavior, refactor, update, modify, or improve code in a project that has shipwright_run_config.json with status complete. Also when user describes a bug report, enhancement request, or any code-level change to a finished project.\nDO NOT TRIGGER when: user asks about project setup (/shipwright-project), planning (/shipwright-plan), initial build (/shipwright-build), deployment (/shipwright-deploy), running tests (/shipwright-test), or non-code tasks like documentation questions. Also DO NOT TRIGGER when the pipeline is still in_progress — those changes belong to the current pipeline phase."
license: MIT
compatibility: Requires uv (Python 3.11+), git repository required, completed Shipwright project
---

# Shipwright Iterate Skill v0.3.0

Complexity-adaptive change lifecycle for completed Shipwright projects.
Detects intent (feature, change, bug), assesses complexity, runs the right amount of process.

> **How it gets invoked:**
> 1. Directly via `/shipwright-iterate` (explicit)
> 2. Via UserPromptSubmit hook context (automatic — `suggest_iterate.py` detects code-change intent
>    and injects "[Shipwright] Detected: ..." context into the prompt)

> **External review machinery (shared, since v0.5.x):** medium+ iterate runs
> use `{shared_root}/scripts/tools/external_review.py --mode iterate` for the
> external LLM review and `{shared_root}/scripts/checks/check-external-review-keys.py`
> + `mark-review-state.py` for the interactive review gate (Branch A/B/C
> mirroring the plan flow). `{shared_root}` resolves to the monorepo's
> `shared/` directory.

---

## Phase Index

```
Repo Scout, Mini-Plan, Escape Hatch   → references/iteration-planning.md
Self-Review, Full Review, Handoff      → references/iteration-reviews.md
Design Check, Testing, Visual, E2E     → references/design-and-testing.md
Reflection Protocol                    → references/reflection.md
Boundary Probe — edge-case checklist   → references/boundary-probes.md
Boundary Probe — round-trip patterns   → references/round-trip-tests.md
Confidence Calibration — anti-patterns → references/confidence-anti-patterns.md
Risk Taxonomy, Override Classes        → this file (inline)
Phase Matrix                           → this file (Section 6, NORMATIVE)
```

---

## CRITICAL: First Actions

**Governing rules:** Read and follow `shared/constitution.md` (ALWAYS / ASK FIRST / NEVER boundaries).

**BEFORE using any other tools**, do these in order:

### A. Print Intro Banner

```
================================================================================
SHIPWRIGHT-ITERATE v0.3.0: Adaptive Change Lifecycle
================================================================================
Keeps specs, tests, and ADRs in sync for ongoing changes.
Phases scale automatically based on change complexity.

Usage: /shipwright-iterate --type feature|change|bug "description"
   or: Auto-detected from your prompt (via hook context)

Paths (phases in brackets are complexity-dependent):
  FEATURE  → [interview] → [spec] → [plan] → [approval] → [review] → [design] → build → test → commit
  CHANGE   → [interview] → [spec] → [plan] → [approval] → [review] → [design] → build → test → commit
  BUG      → [spec] → reproduce → [plan] → fix → test → commit

Complexity: trivial | small | medium | large (auto-detected, overridable)
================================================================================
```

### B. Validate Project

1. Verify `shipwright_run_config.json` exists in the project root
2. Verify `status` is `"complete"` or iterate_history exists (iterate is for post-pipeline changes)
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

### B1. Check for a Resumable Iterate Run

Every iterate run lives in its own git worktree under `.worktrees/<slug>/`
(created unconditionally by **Worktree Isolation**, B1a below). Before
starting fresh, check whether a previous run was interrupted and is
resumable:

1. **Already inside a worktree?** If `git rev-parse --git-common-dir`
   resolves to a `.git` directory ABOVE the cwd, the skill is already
   running inside a worktree — THIS is the run. Read
   `.shipwright/agent_docs/session_handoff.md`, treat the cwd as
   `{project_root}`, and resume in place. Skip the rest of B1 and skip
   B1a (the worktree already exists).
2. Otherwise enumerate `iterate/*` branches + their worktrees (read-only;
   exits 1 only on hard git failures):
   ```bash
   uv run "{shared_root}/scripts/tools/list_iterate_branches.py" --project-root .
   ```
   - `locked` = a branch live in an existing `.worktrees/<slug>/` — a
     resumable run; surface it as a resume candidate.
   - `stale` = merged; print a housekeeping hint:
     `git branch -D iterate/X` (and `git worktree remove .worktrees/X` if a
     worktree lingers).
   - If `main` AND `master` both exist, pass `--main <name>` explicitly.
3. Check `.shipwright/agent_docs/session_handoff.md` for a referenced run_id.

**If a resumable run is detected:**

```
================================================================================
SHIPWRIGHT-ITERATE: Resumable Run Detected
================================================================================
Run ID:     {run_id from handoff or branch name}
Branch:     iterate/{slug}
Worktree:   .worktrees/{slug}/
Phase:      {last phase from handoff, or "unknown"}

Options:
  1. Resume   — continue in that worktree
  2. Abandon  — discard it (worktree + branch removed)
  3. Complete — skip to finalization (F0-F12) in that worktree

To start UNRELATED work, just describe it — a fresh, separate worktree is
created automatically. Parallel iterate runs need NO special mode:
isolation is structural (see B1a).
================================================================================
```

**Wait for user choice.**

- **Resume:** `cd` into `.worktrees/{slug}/` and treat that path as
  `{project_root}` for the rest of the run. Read
  `.shipwright/agent_docs/session_handoff.md` for full state (completed
  phases, remaining work, test status, blocked items). Skip Steps C-G and
  skip B1a — reuse the existing run_id, branch, worktree, and iterate spec.

  **Mandatory replay check (BEFORE dispatching to the Remaining phase).**
  Mandatory phases are not skippable just because a previous session advanced
  past them. The handoff's "Remaining" pointer is an advisory hint, not proof
  that earlier phases actually ran — the generic Stop hook that writes the
  handoff does not persist phase-progress markers. Verify explicitly:

  1. **External LLM Review (medium+ only).** Check `.shipwright/planning/iterate/` for a
     completion marker. Acceptable evidence: either
     `.shipwright/planning/iterate/{run_id}-external-review.json`, OR
     `.shipwright/planning/iterate/external_review_state.json` with a `timestamp` newer
     than the iterate spec's mtime. If neither exists and complexity is
     medium+ with `feedback_iterations > 0`, run Step 4 (External LLM Review)
     FIRST, then continue. Trivial/small iterates skip this check.
  2. **Self-Review.** Grep the iterate ADR for a `Self-Review:` block. If
     absent, run Step 7 before commit — self-review is mandatory at every
     complexity level.

  Only after both checks pass, dispatch to the phase listed under "Remaining"
  in the handoff (fall back to Build if no Remaining section is present — the
  current handoff generator does not write one).
- **Abandon:** `git worktree remove --force .worktrees/{slug}` then
  `git branch -D iterate/{slug}`; remove `.shipwright/agent_docs/session_handoff.md`
  if it referenced that run. Proceed with a fresh run (continue to B1a).
- **Complete:** `cd` into `.worktrees/{slug}/`, treat it as `{project_root}`,
  skip to Finalization (F0-F12). **Same replay check applies** — run External
  Review / Self-Review first if markers are missing, before F0.

**If no resumable run is detected:** continue to B1a (Worktree Isolation).

### B1a. Worktree Isolation (unconditional)

**Every iterate run executes in its own git worktree + branch + PR — always,
structurally, with no opt-in and no detection.** This is the one mechanism
that makes parallel iterate runs safe: two runs can never share a working
tree, race a `git checkout -b`, or cross-write each other's changes. The
former "Parallel" menu option and the canonical/secondary session-role
machinery are gone — they were a workaround for isolation that was
*conditional* instead of *structural*.

Run this BEFORE B2 and before writing ANY artifact, as soon as the slug is
known. Derive `<slug>` as a short kebab-case description of the change and
`<run_id>` as `iterate-{YYYY-MM-DD}-{slug}` (Step C formalizes the same
values):

```bash
uv run "{shared_root}/scripts/tools/setup_iterate_worktree.py" \
  --project-root . --slug "<slug>" --run-id "<run_id>"
```

The helper detects main-repo vs. worktree:

- **Main repo** → `git fetch origin`, then
  `git worktree add .worktrees/<slug> -b iterate/<slug> origin/<default>`.
  The branch base is ALWAYS freshly-fetched `origin/<default>` — never local
  `main`, never another `iterate/*`. It also snapshots the main tree (for the
  F0/F11 leak-guard) and writes a per-session run pointer.
- **Already inside a worktree** → no-op.

Parse the JSON on stdout. **For the entire rest of this run, `{project_root}`
is the `project_root` field of that JSON** — the new worktree path on a fresh
run. Also `cd` the shell into it (belt-and-suspenders). From here on EVERY
file / git / test / build operation is rooted at `{project_root}`: use
`git -C`, absolute paths, `npm --prefix`, `uv run --directory` — never
`cd <subdir> && …`.

> **The session process cwd does NOT move.** It stays at the project root so
> webui session-JSONL discovery is unaffected. Only `{project_root}` (this
> skill's path variable) and the Bash shell cwd point into the worktree.

**Exit codes:** `0` ok · `2` slug collision — pick a different slug or clean
up the existing `.worktrees/<slug>` / `iterate/<slug>` · `3` `git fetch`
failed — **STOP**, unless the operator deliberately sets
`SHIPWRIGHT_ITERATE_NO_FETCH=1` for offline use (the run may then start from
a stale base — the deliberate trade-off).

**Worktree conventions:**

- One iterate = one worktree = one branch = one PR.
- `.worktrees/<slug>` lives inside the repo and is `.gitignore`'d.
- Worktrees carry neither `node_modules`/`.venv` nor `.env*`. Re-hydrate as
  the project shape requires: copy `.env*` from the main repo, then run the
  install commands that apply (`npm install`, `uv sync`, …). Probe file
  existence first — a Python-only project gets no `npm install`.
- Disjoint file scopes still matter: if two concurrent iterates touch the
  same file they will conflict at PR-merge time. Rebase-per-PR against
  current `origin/<default>` is expected when multiple PRs are open.
- Cleanup after the PR merges: `git worktree remove .worktrees/<slug>` then
  `git branch -D iterate/<slug>`. The `list_iterate_branches.py` helper shows
  which branches are `locked` (live in a worktree) vs `stale` (safe to delete).

See `docs/guide.md` chapter "Parallel Development with Worktrees".

### B2. Load Project Context (MANDATORY)

**Read ALL of these files NOW before proceeding.** This context is required for accurate intent classification, complexity assessment, and interview questions. Do NOT skip this step.

> All paths below are under `{project_root}` — the worktree created in B1a.
> Read from the worktree (fresh from `origin/<default>`), not the main repo.

1. `CLAUDE.md` — stack, conventions, commands
2. `.shipwright/agent_docs/conventions.md` — coding standards, naming, patterns
3. `.shipwright/agent_docs/decision_log.md` — ALL architectural decisions (read the complete file)
4. `.shipwright/agent_docs/architecture.md` — app structure, component tree, data flow
5. `shipwright_sync_config.json` — file-to-FR mappings (if exists)
6. `.shipwright/planning/*/spec.md` — ALL spec files across all splits (read completely)
7. `shipwright_test_results.json` — last test run status, degraded conditions
8. `shipwright_events.jsonl` — ALL events — complete project history (work_completed, deployments, etc.)
9. Run: `git log --oneline -20` — recent commits (prevents duplicate work)

Note: `shipwright_run_config.json` was already read in Step B (Validate Project).

If a file does not exist, skip it but print WARNING: "Operating with incomplete project context — missing: {list of missing files}". Not all projects have all artifacts, but the warning helps diagnose unexpected behavior downstream.

### C. Generate Run ID

Generate `run_id`: `iterate-{YYYY-MM-DD}-{short-description}`
Example: `iterate-2026-04-05-course-search`

The dashed-date form is the canonical run_id shape — `RUN_ID_STRICT` in
`shared/scripts/lib/iterate_entry.py` and `append_iterate_entry.py` (F5c)
enforce it; every historical run_id uses it.

This ID is propagated through ALL artifacts: iterate spec, mini-plan, ADR, event log, iterate_history, session handoff.

### D. Determine Intent Type

**Priority order for type detection:**

1. **Explicit flag:** `--type feature|change|bug` from invocation
2. **Hook context:** Parse `[Shipwright] Detected: FEATURE|CHANGE|BUG` from additionalContext
3. **Auto-classify:** Run the classifier:
```bash
uv run "{plugin_root}/scripts/lib/classify_intent.py" \
  --message "{user_message}" \
  --sync-config "{project_root}/shipwright_sync_config.json"
```
4. **Ask user:** If confidence < 0.7 or type is "none", ask:
   > What type of change is this?
   > - **Feature** — new functionality
   > - **Change** — modify existing behavior
   > - **Bug** — fix something broken

### E. Assess Complexity (Two-Stage)

#### Stage 1: Quick Estimate

```bash
uv run "{plugin_root}/scripts/lib/classify_complexity.py" \
  --message "{user_message}" \
  --sync-config "{project_root}/shipwright_sync_config.json"
```

Parse JSON output: `estimate`, `confidence`, `risk_flags`, `enforcements`, `signals`.

User can override: `--complexity trivial|small|medium|large`
Safety floor: risk flags still enforce minimums even when overridden (see Override Classes below).

#### Stage 2: Repo Scout

Confirm or upgrade the estimate. See `references/iteration-planning.md` for protocol.

- **Quick Scout** (trivial/small estimate): check affected files + verify risk flags
- **Thorough Scout** (medium estimate): read specs, check cross-split, identify shared components

**Required outputs** (printed in Planned Run Summary):
- Affected files list (estimated)
- Affected FRs
- Risk flags triggered
- Cross-split: yes/no
- Final complexity with reasoning

**After Stage 2, complexity is locked** (unless mid-flight escalation, see Section 7).

### F. Print Planned Run Summary

```
================================================================================
SHIPWRIGHT-ITERATE: Session Plan
  Run ID:      {run_id}
  Intent:      {FEATURE | CHANGE | BUG}
  Complexity:  {level} ({reasoning})
  Risk flags:  {list or "none"}
  Phases:      {phase list from matrix}
  Skipping:    {skipped phases with reason}
  Safety floor: {enforcements if any}
================================================================================
```

User can adjust: "make it medium", "skip design", "skip review".
See Override Classes below for what can and cannot be skipped.

### G. Interview (complexity-gated)

After the Planned Run Summary, ask clarifying questions BEFORE writing specs or code.
This replaces manual Plan Mode — iterate handles scoping automatically.

**CRITICAL: Wait for user answers before proceeding to any path step.**

| Complexity | FEATURE | CHANGE | BUG |
|------------|---------|--------|-----|
| Trivial | skip | skip | skip (reproduce instead) |
| Small | 1 confirmation Q | 1 confirmation Q | skip (reproduce instead) |
| Medium | 2-3 scoping Qs | 1-2 scoping Qs | skip (reproduce instead) |
| Large | → escape hatch | → escape hatch | → escape hatch |

#### Small — Confirmation (1 question, FEATURE + CHANGE)

> "Do I understand correctly: [restate intent in 1 sentence]. Shall I proceed with this?"

- If user corrects → apply Feedback Parsing Protocol (above), then update scope, re-assess complexity if needed.
- If user confirms → proceed to Step 1 of the relevant path.

#### Medium — FEATURE (2-3 questions)

1. "What exactly should the feature do? (Brief description + Acceptance Criteria)"
2. "What is explicitly out of scope?"
3. [If UI] "How should it look/behave?"

Use answers to populate the Iterate Spec (Step 1).

#### Medium — CHANGE (1-3 questions)

1. "What exactly should change and why?"
2. "Are there related areas that should remain unchanged?"
3. [If UI change] "Which screen mockup(s) from .shipwright/designs/screens/ show the target state?"

Use answers to populate the Iterate Spec (Step 1) and scope the Spec Update (Step 2).

### Feedback Parsing Protocol (applies to Interview, Approval Gate, and any user correction)

When the user provides feedback (corrections, additions, scope changes):

1. **Extract ALL items** — read the entire user message, decompose into individual items
2. **Numbered checklist** — echo all extracted items back as a numbered list:
   > "Here's what I got from your feedback:
   > 1. [Item 1]
   > 2. [Item 2]
   > 3. [Item 3]
   > Did I capture everything, or is something missing?"
3. **Wait for confirmation** — only proceed after user OK
4. **Track as tasks** — add each confirmed item as a task (TodoWrite), mark completed once implemented
5. **No silent dropping** — if an item is not feasible, communicate explicitly why

**CRITICAL: NEVER proceed to the next step without all feedback items captured and confirmed.**

---

## Canonical Risk Taxonomy

One authoritative list, referenced everywhere in this skill.

| Risk Flag | Trigger Paths | Min Complexity | Enforces |
|---|---|---|---|
| `touches_auth` | `src/middleware.ts`, `src/lib/supabase/`, `**/auth/**` | small | mandatory review |
| `touches_rls` | `supabase/migrations/*rls*`, RLS policy changes | small | mandatory review |
| `touches_middleware` | `src/middleware.ts`, `next.config.*` | small | mandatory review |
| `touches_migrations` | `supabase/migrations/` | small | mandatory review + down.sql |
| `touches_billing` | `**/stripe/**`, `**/payment*/**`, webhook handlers | small | mandatory review |
| `touches_shared_infra` | `src/lib/`, `src/components/ui/`, layout components | small | full test suite |
| `cross_split` | changes span 2+ planning splits | medium | full review + full test suite |
| `touches_public_api` | API route handlers, exported types | small | mandatory review |
| `touches_build` | `package.json`, `*-lock.*`, `next.config.*`, `vite.config.*`, `tailwind.config.*`, `webpack.config.*`, `rollup.config.*`, `tsconfig.json` | small | performance test layer (Lighthouse + bundle gate via /shipwright-test Step 3.8) |
| `touches_io_boundary` | `.env*`, `hooks.json`, `settings.json`, `*_config.json`, `*_state.json`; or anchored producer/consumer keywords (`parse_env`, `json.dump(s)?`, `json.load(s)?`, `yaml.dump`, `yaml.safe_load`) | small | round-trip test (Boundary Probe sub-step in Build TDD — see `references/boundary-probes.md` + `references/round-trip-tests.md`) |

Note: "touches_db" (ordinary query/model edits without schema changes) is NOT a risk flag.

Note: `touches_build` triggers `/shipwright-test`'s Performance Budget step
(Step 3.8). Behavior follows the project's profile/test_config (`warn` default,
`block` opt-in). Skip-rules from Step 3.8 still apply (no `dev_url` → skip
Lighthouse, no build artifacts → skip bundle).

---

## Override Classes

| Category | Phases | User can skip? |
|---|---|---|
| **Mandatory** | Self-review, unit test, commit, ADR, compliance, test results JSON, iterate_history, Confidence Calibration (medium+) | Never skippable |
| **Safety-enforced** | Full review (when risk flags), full test suite (when shared infra), down.sql (when migrations), Boundary Probe (when `touches_io_boundary`), Confidence Calibration (small with `touches_io_boundary`) | Only with explicit risk acknowledgment |
| **Advisory** | Design check, mini-plan, design fidelity, E2E update, external LLM review, release prompt, Confidence Calibration (trivial / small without `touches_io_boundary`) | Freely skippable |
| **Complexity-gated** | Iterate spec, context scan depth | Adjustable via "make it medium/small" |

---

## Context Loading (Progressive Disclosure)

### Layer 1 — Always Load (read in Step B2)

1. `shipwright_run_config.json` — project metadata, profile, completed sections
2. `CLAUDE.md` — project conventions, stack, commands
3. `.shipwright/agent_docs/conventions.md` — coding standards, naming, patterns
4. `.shipwright/agent_docs/decision_log.md` — ALL architectural decisions (read completely)
5. `.shipwright/agent_docs/architecture.md` — app structure, component tree, data flow
6. `shipwright_sync_config.json` — file-to-FR mappings (if exists)
7. `.shipwright/planning/*/spec.md` — ALL spec files across all splits (read completely)
8. `git log --oneline -20` — recent commits (prevents duplicate work)
9. `shipwright_test_results.json` — last test run status, degraded conditions
10. `shipwright_events.jsonl` — ALL events — complete project history (work_completed, deployments, etc.)

### Layer 2 — Load On-Demand

Read only when the change touches their domain:

- `.shipwright/planning/*/sections/*.md` — only the section files for affected areas
- `.shipwright/designs/visual-guidelines.md` — only for UI changes
- `.shipwright/designs/screens/*.html` — only for UI changes requiring mockup reference
- `.shipwright/designs/chrome-definition.md` — only for UI changes needing chrome context
- `{build_plugin_root}/skills/build/references/shadcn-rules.md` — Core Rules only, for UI changes
- `{build_plugin_root}/skills/build/references/shadcn-project-conventions.md` — Card/Button conventions, for UI changes
- `{build_plugin_root}/skills/build/references/shadcn-block-patterns.md` — Index + matching category only
- `{build_plugin_root}/skills/build/references/mockup-to-shadcn-mapping.md` — for UI changes
- `supabase/migrations/` — only for database changes

Where `{build_plugin_root}` = path to `plugins/shipwright-build` (resolve from `shipwright_run_config.json` or relative to shared).

---

## Path A: FEATURE (new functionality)

Follow the Phase Matrix (Section 6) to determine which steps run.

### Step 1: Iterate Spec (medium+ only)
Create `.shipwright/planning/iterate/{date}-{short-description}.md` using this template:

```markdown
# Iterate Spec: {short-description}

- **Run ID:** {run_id}
- **Type:** {feature | change | bug}
- **Complexity:** {level}
- **Status:** draft

## Goal
{1-2 sentences — populated from interview answers (Section G)}

## Acceptance Criteria
- [ ] {AC from interview — concrete, testable}
- [ ] {AC 2}

## Spec Impact
{Classify how this iterate changes the FR spec — see Step 2.}
- **Classification:** {add | modify | remove | none — one or more}
- **ADD** (new FR appended): {FR-XX.YY — short title, or `none`}
- **MODIFY** (existing FR changed): {FR-XX.YY — what changed, or `none`}
- **REMOVE** (FR retired → `## Removed Requirements`): {FR-XX.YY, or `none`}
- **NONE justification:** {required only when Classification is solely
  `none` — why this feature/change touches no FR}

## Out of Scope
- {from interview answer — what explicitly will NOT be done}

## Design Notes
{Filled during Design Check. Include:
 - Affected mockup files from .shipwright/designs/screens/ (e.g. "10-kanban-board.html")
 - Design tokens applied (colors, spacing, typography)
 - New vs modified components
 - Deviations from visual guidelines with justification}

## Affected Boundaries
{Producer/consumer pairs for any changed serialized format.
 Triggers Boundary Probe sub-step in Build TDD when `touches_io_boundary`
 risk flag fires (or when any IO_BOUNDARY_FILE_PATTERNS match the diff).

| Producer (writes) | Consumer (reads) | Format |
|---|---|---|
| {file:fn} | {file:fn} | {env / JSON / YAML / ...} |

If no boundaries touched: write `n/a` with one-line justification.}

## Confidence Calibration
{Mandatory at medium+; mandatory at small when `touches_io_boundary`
 fires. Empirical probes run before F0 Fresh Verification Gate. See
 SKILL.md Path A Step 7.5 + `references/confidence-anti-patterns.md`.

- **Boundaries touched:** {list from "Affected Boundaries" above}
- **Empirical probes run:** {one-line per probe + finding — real
  round-trip / edge-case tests, not "I re-read the diff". Source:
  the 8 categories in references/boundary-probes.md plus any
  format-specific probes}
- **Edge cases NOT probed + why acceptable:** {one line per skipped
  category, with rationale. Operator-input categories may be skipped
  for machine-only formats with justification}
- **Confidence-pattern check:** {has any "are you confident?"-style
  question already produced "yes" + a subsequent finding in this
  run? If yes, run one more probe before F0 — asymptote heuristic}}

## Verification (medium+)
{Mandatory at medium+. The runner that will produce the F0.5
 surface_verification block.

- **Surface:** web | cli | api | none
- **Runner command:** {exact command F0.5 will execute, e.g.
  `npx playwright test e2e/flows/foo.spec.ts` or
  `uv run pytest plugins/shipwright-iterate/tests/ -v`}
- **Evidence path:** {where output lands, e.g. `playwright-report/index.html`,
  pytest log file, or curl response file}
- **Justification (only if surface=none):** {one line — why no startable
  surface exists for this change. Referenced in iterate ADR.}}
```

### Step 2: Spec Update — classify the Spec Impact (always)
1. Identify which spec file(s) cover the affected area.
2. **Classify the spec impact** as one or more of ADD / MODIFY / REMOVE,
   or NONE. Record it in the iterate spec's `## Spec Impact` section
   (medium+) and carry the same FR IDs into F7 (`--spec-impact`,
   `--affected-frs`, `--new-frs`).
   - **ADD** — a new endpoint, page, flow, or user-visible capability:
     append a new FR table row + an acceptance-criteria block. The new
     FR ID goes to F7 `--new-frs` (and `--affected-frs`).
   - **MODIFY** — an additive side-effect or changed behavior of an
     existing FR: update the FR table-row description + append new
     `- (E) Given … when … then …` acceptance-criteria lines covering
     the new behavior + any idempotency / no-op guarantees. The FR ID
     goes to F7 `--affected-frs`. Reference the run_id + ADR.
   - **REMOVE** — the change deletes a user-visible capability: move the
     FR row out of `## 2. Functional Requirements` into a
     `### Removed Requirements` subsection — never silently delete it.
     The moved row keeps its ID + text + priority and adds the run_id and
     the literal `status: deprecated`. See
     `plugins/shipwright-project/skills/project/references/spec-generation.md`.
   - **NONE** — a behavior-preserving internal refactor with no
     user-visible change. Record a one-line justification; it is passed
     to F7 as `--spec-impact none --spec-impact-justification "..."`.
3. **NONE is a classification that must be *justified*, not a default.**
   The Phase Matrix marks this step `always` for FEATURE — that is
   load-bearing. "Additive" or "small" is a reason the update is *small*,
   not a reason to skip it. The F11 finalization verifier
   (`check_spec_impact_recorded`) FAILS a feature/change iterate whose
   commit touched no `spec.md` unless `spec_impact=none` + a justification
   was recorded at F7.
4. If `shipwright_sync_config.json` exists, add/update mappings for the
   affected files.

> **AC shape (medium+).** ACs MUST be assertion-shaped (mechanically
> verifiable by the F0.5 runner), not story-shaped. Story: "user can save
> the form". Assertion: "POST /api/forms returns 200; subsequent GET
> returns the saved record". Story-shaped ACs cannot be empirically
> driven through the surface runner and silently degrade F0.5 to
> spec-only authorship.

### Step 3: Mini-Plan (small: inline, medium: persisted)
See `references/iteration-planning.md` for protocol.
- Small: inline in session
- Medium+: save as `.shipwright/planning/iterate/{date}-{desc}-miniplan.md`

### Step 3b: User Approval Gate (medium+)

Present the iterate spec + mini-plan summary to the user:

> "Here is my plan:
> - **Scope:** {AC summary from iterate spec}
> - **Approach:** {mini-plan summary: files to change, work breakdown, test strategy}
> - **Out of scope:** {boundaries from iterate spec}
>
> Shall I proceed, or would you like to adjust scope, ACs, or approach?"

**CRITICAL: Wait for user approval before proceeding to build.**

- If user adjusts → apply Feedback Parsing Protocol, update iterate spec + mini-plan for EACH item, re-present complete summary
- If user approves → proceed to Step 4

For trivial/small: skip (the confirmation question in Section G is sufficient).

### Step 4: External LLM Review (medium auto, or --review flag)
See `references/iteration-planning.md` for invocation.

### Step 5: Design Check (if UI)
See `references/design-and-testing.md` for 2-tier protocol.

### Step 6: Build (TDD — Red-Green-Refactor)
1. The worktree and branch `iterate/<slug>` already exist — created
   unconditionally in B1a (Worktree Isolation) from freshly-fetched
   `origin/<default>`. Do NOT run `git checkout -b`. All build work happens
   in `{project_root}` (the worktree); use `git -C "{project_root}"`.
2. **RED — Write failing tests first**, at minimum one test per Acceptance Criteria:
   - Tests assert on **outcomes, not internal state**
   - At least one **happy-path AND one error-path** test per AC
   - **User interactions:** onClick/onSubmit/onChange triggers the expected action (not just "renders without error")
   - **Form submissions:** input → submit → API/DB call is invoked with correct data
   - **API calls:** correct endpoint, correct parameters, error case handled
   - **Data persistence:** create/update/delete triggers the correct DB/API call
   - No tests that always pass regardless of implementation
   - **Test-Update-Klausel** — when an iterate changes **test infrastructure
     itself** (skip semantics, hygiene rules, test conventions, the
     iterate skill's own checklist), the iterate MUST update the
     skill's reference rules in the same diff. Test fixes that don't
     codify the underlying rule re-introduce the same anti-pattern on
     the next iterate. Concretely: if you tighten a skip rule in
     tests, document the rule here in Step 6, not only in the test
     file's comments. Origin: ADR (this iterate),
     iterate-2026-05-11-test-hygiene-and-skill-rules AC-5.
   - **Registry-driven SSoT meta-test rule** — when a registry (dict /
     list / map of strings) in `shared/scripts/lib/*` references files
     or identifiers on disk, **both directions** of drift protection
     MUST exist: (a) forward — every registry value resolves to a
     real file; (b) reverse — every file matching the registry's
     namespace pattern has a registry entry. Canonical example:
     `shared/tests/test_ci_workflow_convention.py` (forward) +
     `shared/tests/test_ci_template_registry_completeness.py` (reverse,
     added in this iterate). Without the reverse test, orphan files
     accumulate undetected — see ADR-043 / iterate-2026-05-10 for the
     two zero-caller orphans that motivated this rule.
   - **Silent-skip CI-discipline rule** — `pytest.skip(...)` on
     missing-binary or cross-plugin sys.path-pollution / ImportError
     paths MUST hard-fail in CI with an actionable install hint.
     Pattern: `if os.environ.get("CI", "").lower() in ("true", "1"): pytest.fail(...)`
     guarding the skip. The install-hint must name a concrete remediation
     (`actions/setup-node@v4`, `astral-sh/setup-uv@v3`, plugin-session
     invocation, etc.). Local dev keeps the skip so single-plugin
     pytest sessions don't blow up. Drift protection lives in
     `shared/tests/test_silent_skip_ci_discipline.py` (added in this
     iterate). Origin: iterate-2026-05-11 — silent skips were
     systematically hiding tooling-absence in CI runs.
3. Run tests — they **MUST fail** (if they pass: you're testing the wrong thing or it's already implemented)
4. **GREEN — Implement** minimum code until tests pass
5. Run tests after each significant change
6. **Verify wiring** — would the test fail if the wiring (onClick → handler → API) is missing? If not: improve the test
6a. **Boundary Probe (when `touches_io_boundary` is set)** — mandatory sub-step
    when the risk flag fires (either via prompt keywords or via
    `is_io_boundary_change(changed_files)` against the diff). Skip rules
    follow Override Classes (Safety-enforced — only skippable with explicit
    risk acknowledgment in the iterate ADR).
    - Identify producer + consumer pair(s) for every changed serialized format
    - Write a real producer→file-on-disk→consumer round-trip test
      (`references/round-trip-tests.md` Section 1)
    - For user-edited formats (env, JSON config operators inspect by hand),
      run all 8 probe categories from `references/boundary-probes.md`
    - For machine-only formats: round-trip test only; operator-input
      categories may be skipped with a one-line justification in Self-Review
    - When the same parser/serializer exists in N places, add the
      duplicated-consumer drift-protection parametrized test
      (`references/round-trip-tests.md` Section 2)
**Migration apply** (if migration files were created during build):

Read `migrations` config from the stack profile (loaded in Step B2).

**Preflight + Apply:**
1. Run `{migrations.preflight_cmd}` — verify environment ready
2. If `safe_nonprod_only` is true, verify target is non-production
3. If preflight fails: Print diagnostic, instruct user to fix. **Stop.**
4. Run `{migrations.apply_cmd}`
5. If apply fails: **Stop immediately.** Do not run tests. Ask user for intervention.
6. Verify with `{migrations.list_cmd}`

**Post-migration manual steps:**
7. Check `post_apply_manual_steps` — match `trigger_tag` against changes
8. If matched: inform user via AskUserQuestion, note blocked test areas, wait for confirmation

Apply immediately after creating the migration, before running tests.

7. Run tests:
```bash
npx vitest run
npx tsc --noEmit

# Integration tests (if CRUD/DB changes)
npx vitest run --config vitest.integration.config.ts

# pgTAP tests (if new RLS migrations)
supabase test db
```

### Step 7: Self-Review (always)
See `references/iteration-reviews.md` for 7-point checklist
(item 7: Affected Boundaries).

### Step 7.5: Confidence Calibration (mandatory at medium+, also when `touches_io_boundary`)

The "are you confident?" question is unfalsifiable. Replace it with
empirical probes per `references/confidence-anti-patterns.md`. Before
F0 Fresh Verification Gate, the runner MUST populate the
**Confidence Calibration** section of the iterate spec with answers
to these four questions (one bullet each):

1. **Boundaries touched:** which producer/consumer pairs from the
   spec's "Affected Boundaries" section apply to this run? (Copy
   the table or reference it by section.)
2. **Empirical probes run:** one line per probe + finding. Probes
   must be real round-trip / edge-case tests, not "I re-read the
   diff". Source: the 8 categories in `references/boundary-probes.md`
   plus any format-specific probes the runner identifies.
3. **Edge cases NOT probed + why acceptable:** one line per skipped
   category, with justification. For machine-only formats:
   operator-input categories (POSIX `export`, inline `# comment`,
   quoted `#`) may be skipped with one-line rationale.
4. **Confidence-pattern check:** has any "are you confident?"-style
   question received "yes" + a subsequent finding in this run? If
   yes, run **one more probe before F0**, regardless of how many
   probes already passed (asymptote heuristic — see
   `references/confidence-anti-patterns.md`).

**Stopping rule.** Declare exhausted only when the most recent probe
returned no finding AND all applicable categories are covered AND no
yes-then-bug pattern has fired in this run.

**Override Classes:** Mandatory at medium+, Safety-enforced at small
with `touches_io_boundary`, Advisory otherwise. Skip rules per
Override Classes (only skippable with explicit risk acknowledgment
in the iterate ADR when Safety-enforced applies).

### Step 8: Full Code Review (conditional)
See `references/iteration-reviews.md` for trigger rules.

### Step 9: Browser Verify + Smoke Test (early signal — see F0.5 for authoritative gate)
See `references/design-and-testing.md`. At medium+, F0.5 is the authoritative
end-to-end gate; Step 9 produces early signal during build but does not
satisfy the gate on its own.

### Step 10: Testing
- Trivial/small: `npx vitest --related $(git diff --name-only HEAD) --run`
- Medium+: `npx vitest run` (full suite)
- Safety floor paths → always full suite
See `references/design-and-testing.md` for details.

### Step 11a: Author E2E Spec (always at medium+; if feature+UI at trivial/small)
See `references/design-and-testing.md` § "End-to-End Verification — Authoring".

### Step 11b: Execute E2E Spec against Dev Stack (always at medium+)
See `references/design-and-testing.md` § "End-to-End Verification — Execution".
**Spec-only authoring without execution is forbidden at medium+.** Execution
is verified at F0.5; the production-time chokepoint is
`shared/scripts/surface_verification.py`.

### Step 12: Design Fidelity (if structural UI)
See `references/design-and-testing.md` for structural extraction + agent deep analysis protocol.

### Step 13: Escalation Check
See Section 7 (Mid-Flight Escalation).

### Step 14: Finalize
Go to **Finalization** below.

---

## Path B: CHANGE (modify existing behavior)

Same steps as FEATURE, with these differences:
- Step 2: see below — same ADD/MODIFY/REMOVE/NONE classification as FEATURE; the default for CHANGE is MODIFY
- Step 6: Update existing tests to reflect new expected behavior, then implement
- Step 6a: Boundary Probe applies identically — when `touches_io_boundary` fires, run the round-trip + 8-probe checklist before commit
- Step 7.5: Confidence Calibration applies identically — mandatory at medium+, also at small with `touches_io_boundary` (see Path A Step 7.5)

### Step 2: Spec Update — classify the Spec Impact (always — CHANGE)
1. Identify which spec file(s) cover the affected area.
2. **Classify the spec impact** as one or more of ADD / MODIFY / REMOVE,
   or NONE — same four cases as FEATURE Step 2. For CHANGE the default
   is **MODIFY**.
   - **MODIFY** (default for CHANGE) — modifying behavior of an existing
     endpoint, page, or component: update the FR table-row description to
     reflect the new behavior + append new `- (E) Given … when … then …`
     acceptance-criteria lines covering the modified behavior + any
     backwards-compatibility / migration guarantees. The FR ID goes to F7
     `--affected-frs`. Reference the run_id + ADR.
   - **ADD** (rare for CHANGE) — only when the modification carves out a
     new user-visible capability alongside the old one: append a new FR
     table row + an acceptance-criteria block; the new FR ID goes to F7
     `--new-frs`.
   - **REMOVE** — the change deletes a user-visible capability: move the
     FR row into a `### Removed Requirements` subsection with the run_id
     and the literal `status: deprecated` (never silently delete).
   - **NONE** — a behavior-preserving internal refactor: record a
     one-line justification, passed to F7 as `--spec-impact none
     --spec-impact-justification "..."`.
3. **NONE must be *justified*, not assumed.** The Phase Matrix marks this
   step `always` for CHANGE — that is load-bearing. Scope size is a
   reason the update is *small*, not a reason to skip it. The F11
   verifier (`check_spec_impact_recorded`) FAILS a feature/change iterate
   whose commit touched no `spec.md` without a recorded `spec_impact=none`.
4. If `shipwright_sync_config.json` exists, update mappings to reflect any
   file moves or renames.

---

## Path C: BUG (fix something broken)

### Step 1: Iterate Spec (medium+ only)
Same as FEATURE Step 1.

### Step 2: Spec Update — classify the Spec Impact (BUG)
A bug fix usually restores intended behavior, so the spec impact is
typically NONE. Classify it anyway:
- **MODIFY** — the spec itself was wrong: correct the FR row / ACs.
- **REMOVE** — the spec described behavior the fix removed: move the FR
  into `### Removed Requirements` with `status: deprecated`.
- **NONE** (default) — the fix restores behavior the spec already
  describes correctly. No FR change.

BUG iterates are NOT gated by the F11 spec-impact verifier — a bug fix
need not touch the spec. Record the classification in the iterate ADR;
ADD does not apply to bug fixes.

### Step 3: Investigate & Reproduce

**Do NOT attempt fixes before completing investigation.**

1. **Reproduce** — trigger the bug reliably. Note exact steps, inputs, and environment.
2. **Localize** — identify which layer fails:
   - UI (render/interaction) → check browser console, DOM state
   - API (request/response) → check network calls, status codes, payloads
   - Data (DB/state) → check queries, migrations, state shape
   - External (third-party) → check service status, API changes
   - [If UI layer] Compare current state against .shipwright/designs/screens/{relevant}.html
     to determine intended behavior before fixing
3. **Root Cause** — trace from symptom to cause. Ask "why?" at each level.
   Do NOT fix the first thing that looks wrong — that's symptom-patching.
4. **Write a failing test** that proves the root cause (not just the symptom):
   - The test must fail for the *identified root cause*, not a side effect
   - If you can't write a targeted test, your root-cause analysis is incomplete — go back to step 3
5. Run the test to confirm it fails:
```bash
npx vitest run --reporter=verbose {test_file}
```

**Circuit breaker:** If 3 fix attempts fail after implementing Step 5, STOP.
Re-evaluate: Is the root cause actually understood? Is the architecture itself the problem?
If yes → escalate to Mid-Flight Escalation (Section 7).

### Step 4: Mini-Plan (medium+ only)
See `references/iteration-planning.md`.

### Step 5: Fix
1. The worktree and branch `iterate/<slug>` already exist — created
   unconditionally in B1a (for a bug the slug carries a `fix-` prefix). Do
   NOT run `git checkout -b`. Fix in `{project_root}` (the worktree).
2. **Fix the root cause** — targeted change, minimal scope. Do not fix symptoms.
3. Run reproducing test to verify it passes
4. Run related tests to verify no regressions
5. **Boundary Probe (when `touches_io_boundary` is set)** — same Path A Step 6a sub-step applies. When the bug touches a serialized format, the fix is incomplete without a producer→file→consumer round-trip test that fails before the fix and passes after.
6. **Confidence Calibration (Step 7.5 in Path A)** applies identically to BUG fixes — mandatory at medium+, also at small with `touches_io_boundary`. Populate the spec's Confidence Calibration section before F0.

### Step 6-14: Same as FEATURE (self-review, code review, testing, escalation, finalize)
Follow the Phase Matrix to determine which steps run for the assessed complexity.

---

## 5b. Campaign Mode (Autonomous Multi-Iterate)

When invoked with `--campaign <slug>` and `--autonomous`, run multiple sub-iterates sequentially without manual gates. This formalizes the ad-hoc orchestration pattern used in iterate 14.

**Flags:** `/shipwright-iterate --campaign <slug> [--autonomous]`

> **Review steps in autonomous-loop briefing (ADR-029).** When briefing a
> sub-iterate-runner under `--autonomous`, include a reminder that the
> runner contract mandates **Step 3.5 (External Plan Review)** and
> **Step 3.7 (Code Review Cascade)** between Build and Finalization for
> medium+ iterates (Step 3.5) and for medium+ / risk-flag / >100-LOC
> iterates (Step 3.7). The runner has no `Agent` tool, so the internal
> code-reviewer subagent is delegated back to the orchestrator (campaign
> mode) — the orchestrator spawns it in parallel with the runner after
> Build, then merges findings into the iterate ADR. Skipping these
> review steps silently is a contract violation under ADR-029; the
> runner must record `reviews.{plan,code,external_code}.status` in its
> result-JSON with an explicit `skipped_*` value when applicable.

### Campaign Setup (interactive, once)

If campaign directory doesn't exist yet:

1. User describes the overarching goal
2. Together, decompose into sub-iterates (each should be trivial–medium complexity)
3. Initialize campaign structure:
```bash
uv run "{plugin_root}/scripts/tools/campaign_init.py" \
  --project-root "$(pwd)" \
  --campaign-slug "{slug}" \
  --intent "{user_intent}" \
  --sub-iterates '{json_array}' \
  --branch-strategy stacked
```
4. Review generated `.shipwright/planning/iterate/campaigns/{slug}/campaign.md` with user

### Autonomous Campaign Loop

**Pre-requisite:** `.shipwright/planning/iterate/campaigns/{slug}/status.json` must exist.

1. **Export env vars:**
```bash
export SHIPWRIGHT_ROOT_SESSION_ID="${SHIPWRIGHT_SESSION_ID}"
export SHIPWRIGHT_LOOP_ID=""  # set after init
```

2. **Generate units file and initialize loop:**
```bash
uv run "{plugin_root}/scripts/tools/campaign_progress.py" list-units \
  --campaign-dir ".shipwright/planning/iterate/campaigns/{slug}" > /tmp/campaign_units.json

uv run "{shared_root}/scripts/lib/autonomous_loop.py" init \
  --state .shipwright/loop_state.json \
  --kind sub_iterate \
  --units-from /tmp/campaign_units.json \
  --branch-strategy stacked \
  --root-session-id "$SHIPWRIGHT_ROOT_SESSION_ID"
```
Extract `loop_id` from stdout. Then: `export SHIPWRIGHT_LOOP_ID="{loop_id}"`.

3. **Loop (repeat until exit code 2):**

```
3a. uv run ... next --state .shipwright/loop_state.json
    → exit 2 = all done → go to step 4
    → Parse JSON: id, spec_path, base_branch, attempt

3b. export SHIPWRIGHT_LOOP_UNIT_ID="{id}"

3c. Spawn sub-iterate-runner subagent:
    result = Task(subagent_type="shipwright-iterate:sub-iterate-runner",
                  prompt=<brief with sub_iterate_id, spec, base_branch, etc.>)

3d. Wait for terminal marker (.shipwright/runs/{loop_id}/{id}/DONE, timeout 30s)

3e. Parse result JSON defensively (fallback to runs/{loop_id}/{id}/result.json)

3f. uv run ... record --state .shipwright/loop_state.json --unit {id} --result '{json}'
    → exit 3 = failure/escalation → go to step 4 (strict-stop)

3g. Update campaign status.json:
    uv run "{plugin_root}/scripts/tools/campaign_progress.py" update-status \
      --campaign-dir ".shipwright/planning/iterate/campaigns/{slug}" \
      --sub-iterate-id {id} --status complete --commit {commit} --branch {branch}

3h. Continue loop
```

4. **Finalize:**
```bash
uv run ... finalize --state .shipwright/loop_state.json
```

5. **Release prompt (F12, once):** Only if ALL sub-iterates are `complete` AND worktree is clean:
   Count unreleased entries in `CHANGELOG.md`. If > 0: *"Run /shipwright-changelog to tag a release?"*
   If any sub-iterate failed or escalated: *"Campaign incomplete; no release prompt."*

**When NOT using `--autonomous`:** skip this section entirely, proceed with normal single-iterate flow.

---

## 6. Phase Matrix by Complexity (NORMATIVE)

**This matrix is the Single Source of Truth for phase selection.** All prose, flow diagrams, and examples MUST be consistent with this table.

Large is a "soft boundary" — force-continue supported with mandatory review + full tests.

| Phase | Trivial | Small | Medium | Large |
|---|---|---|---|---|
| Repo Scout | quick | quick | thorough | → escape hatch |
| Interview | skip | 1 confirmation Q | FEATURE: 2-3 Q, CHANGE: 1-2 Q | → escape hatch |
| Iterate Spec | skip | skip | own file in `.shipwright/planning/iterate/` | — |
| Spec Impact (ADD/MODIFY/REMOVE/NONE) | always (BUG: classify; NONE default) | always (BUG: classify; NONE default) | always (BUG: classify; NONE default) | — |
| Mini-Plan | skip | FEATURE only | yes + alternative (all types) | — |
| User Approval | skip | skip | before build | — |
| External LLM Review | skip | skip | auto | — |
| Design Check | skip | Tier 1 (text) | Tier 2 (markdown) | — |
| Build (TDD) | always | always | always | — |
| Boundary Probe | skip | if `touches_io_boundary` | if `touches_io_boundary` | — |
| Self-Review | always | always | always | — |
| Confidence Calibration | skip | if `touches_io_boundary` | always | always |
| Full Code Review | only if risk flags | only if risk flags | always | — |
| Browser Verify | if UI | if UI | if UI | — |
| Smoke Test | if server up | if server up | if server up | — |
| Unit Test | `--related` | `--related` | full suite | — |
| Integration Test | if CRUD | if CRUD | full suite | — |
| pgTAP DB Test | if new RLS | if new RLS | full suite | — |
| E2E Verification (author + execute) | if feature+UI | if feature+UI or `touches_io_boundary` | always | — |
| Design Fidelity | skip | if structural UI | if UI | — |
| Performance Budget | if `touches_build` | if `touches_build` | if `touches_build` OR if UI | — |
| architecture.md | if structural impact | if structural impact | if structural impact | — |
| Test Results JSON | always | always | always | — |
| run_config iterate_history | always | always | always | — |
| Session Handoff | skip | if needed | if needed | — |
| Release Prompt | always | always | always | — |

> **Note (E2E Verification).** "Always" at medium+ means **author AND
> run**, not author OR run. Spec-only authorship counts as no test (see
> F0.5). Large iterates route to the escape-hatch pipeline, which has
> its own E2E gates.

---

## 7. Mid-Flight Escalation

The agent can upgrade complexity mid-flight if scope is expanding.

**Escalation rules:**
- trivial → small: Add self-review (if not running), widen test scope
- small → medium: Backfill in order:
  1. Create iterate spec retroactively
  2. Create mini-plan (document what was done + what remains)
  3. Run external LLM review BEFORE further code changes
  4. Continue at medium level
- any → large: Differentiated by state:

| When detected | State | Action |
|---|---|---|
| During Repo Scout / Planning | Clean | Clean transition → escape hatch |
| During Build | Dirty (code partially written) | WIP checkpoint commit, then escape hatch with user choice: revert + pipeline, or continue |
| During Test | Dirty (tests failing) | Same as build, handoff notes test failures |

See `references/iteration-planning.md` for escape hatch protocol.

**Implementation:** After build and after test, check: "Did actual scope exceed estimated complexity?" If yes, upgrade.

---

## 8. Escape Hatch

When complexity = large, print scope assessment with two options.
See `references/iteration-planning.md` for full protocol including handoff file format and failure behavior.

---

## 9. Artifact Ownership

| Artifact | Owns | Do NOT duplicate here |
|---|---|---|
| **Iterate spec** (`.shipwright/planning/iterate/`) | Intent, ACs, scope, out-of-scope, Spec-Impact classification | Rationale (→ ADR), structure (→ architecture) |
| **spec.md** (FR table + `## Removed Requirements`) | Normative FR changes — ADD/MODIFY in the FR table, REMOVE into the Removed Requirements section | Why (→ ADR), approach (→ mini-plan) |
| **`shipwright_events.jsonl`** (F7 event) | Machine-of-record `spec_impact` classification (enforced by `check_spec_impact_recorded`) | Narrative (→ ADR), FR text (→ spec) |
| **ADR** (`decision_log.md`) | Rationale, alternatives, consequences | Full ACs (→ spec), structure (→ architecture) |
| **architecture.md** | Current structural state | Decisions (→ ADR), requirements (→ spec) |
| **Mini-plan** (`.shipwright/planning/iterate/`) | Approach, files, test strategy | Requirements (→ spec), decisions (→ ADR) |

---

## Finalization (all paths)

**CRITICAL: Steps F0–F11 (including F3a, F5a, F5b, F5c) are MANDATORY. Do NOT skip any step.**

> **Order matters.** F0.5/F3/F3a/F4/F5/F5a/F5b/F5c all write tracked
> artifacts and MUST run before F6 so a single atomic commit stages them.
> F0.5 is the production-time E2E gate — a non-zero exit there blocks the
> entire flow at the verification step, before any artifact is written.
> F7 is the only step that legitimately runs after F6 (it needs the commit
> hash and writes only to a gitignored event log). Do not reorder.

### F0: Fresh Verification Gate

**Leak-guard first.** Confirm the run is still isolated — `{project_root}`
is an iterate worktree and nothing leaked into the main repo working tree:
```bash
uv run "{shared_root}/scripts/checks/check_iterate_isolation.py" \
  --project-root "{project_root}" --run-id "{run_id}" --stage f0
```
Non-zero exit = **STOP**: either the run is not executing in a worktree, or
it wrote into the main tree (compared against the B1a Step-1 snapshot).
Investigate and revert before continuing.

Run the full test suite NOW — do not rely on earlier results:
```bash
npx vitest run
npx tsc --noEmit

# Integration tests (if CRUD/DB changes)
npx vitest run --config vitest.integration.config.ts

# pgTAP tests (if new RLS migrations)
supabase test db
```

**Read the actual output.** Verify:
- Exit code is 0
- All tests pass (not "mostly pass" or "known failures")
- No type errors

If ANY test fails: **STOP.** Go back to the build step and fix before continuing.
Do not proceed to F1 with failing tests.

**If profile has UI and all tests pass:**
```
→ Run /shipwright-preview to verify changes visually before committing.
  Preview URL: {dev_url from shipwright_build_config.json}
```

### F0.5: End-to-End Verification Gate

**Mandatory at medium+. Safety-enforced at small with `touches_io_boundary` or UI.
Advisory at trivial.**

This is the single authoritative gate verifying that the user-erlebbare Surface
was empirically driven through a running stack. Steps 9 and 11 produce early
signal; F0.5 is what F6 commits against. A non-zero exit from F0.5 is **STOP** —
do not proceed to F1.

**Step 1 — Determine Behavior Surface.** Pick exactly one (or `none` with
justification):

- `web` — Playwright against `dev_server.py` (default for web profiles)
- `cli` — scripted CLI / skill / pytest invocation against fixture
- `api` — HTTP probe against running server (API-only changes, no UI)
- `none` — no startable surface; `justification` is mandatory and the
  reason is referenced in the iterate ADR

**Step 2 — Run the Surface Runner.** See `references/design-and-testing.md` →
"End-to-End Verification — Execution" for the per-surface protocol. Inherits
the 3-retry browser-fixer pattern from build's Step 4.5; cap at 3, fail-closed
after.

```bash
uv run "{shared_root}/scripts/surface_verification.py" \
  --project-root "{project_root}" \
  --run-id "{run_id}" \
  --surface "{web|cli|api|none}" \
  [--justification "..."]   # required when surface=none
```

The orchestrator writes raw evidence to
`{project_root}/.shipwright/runs/{run_id}/surface_verification.json`.

**Step 3 — Stage Evidence for F5.** F5 (Test Results JSON) consolidates the
F0.5 raw output into `shipwright_test_results.json.iterate_latest.surface_verification`:

```json
"iterate_latest": {
  ...,
  "e2e": { ... },                  // existing, unchanged
  "surface_verification": {        // NEW
    "surface": "web|cli|api|none",
    "runner": "<command that ran>",
    "exit_code": 0,
    "tests_run": 0,                // > 0 unless surface=none
    "evidence_path": "<path to log/screenshot/playwright-report>",
    "timestamp": "<ISO8601>",
    "justification": "<required when surface=none>"
  }
}
```

Backwards-compat: existing readers (compliance `data_collector.py`,
`test_evidence.py`) only see the new key when they read it — old readers do
not break.

**Fail-closed conditions.** `surface_verification.py` exits non-zero on any of:

1. `surface != "none"` AND `tests_run == 0` (greedy filter matched zero specs —
   critical Playwright failure mode where `--grep` mismatch still returns
   exit 0).
2. `exit_code != 0` from the runner after the 3-retry cap.
3. `surface == "none"` without a `justification`.
4. The `surface_verification` block is missing entirely at medium+ when no
   `surface: none` opt-out is recorded (post-commit audit in
   `verify_iterate_finalization.py`; runtime mitigation: F0.5 is mandatory at
   medium+, so reaching F1 without the block requires explicit prose-violation
   by the agent).

A non-zero exit at F0.5 means STOP — do **not** proceed to F1. F0.5 is the
production-time chokepoint; the post-commit audit in
`verify_iterate_finalization.py` is the second layer.

**Backend-affects-Frontend rule.** If the diff touches API routes, store
mutations, SSE / WS handlers, message contracts, or any code consumed by the
UI — `surface = web` is mandatory even when no `client/**` file changed. The
`always` cell in the Phase Matrix subsumes detection: at medium+, the gate
runs regardless of file paths.

**Spec-only authorship is regression-equivalent to no test.** Authoring a
Playwright / pytest / curl spec without executing it counts as `tests_run = 0`
and fails the gate. The "always" semantics in the matrix mean
**author AND run**, not author OR run.

### F1: Drift Check

```bash
uv run "{shared_root}/scripts/artifact_sync.py" \
  --project-root "{project_root}" --ref "HEAD~1..HEAD"
```

If drift detected, update specs. If iterate spec exists (medium+), check off completed ACs and update status to `implemented`.

### F2: Architecture Update (conditional)

Check ANY of:
- New route / endpoint, OR existing route gaining a materially new behavior
- New component / page
- New schema / migration
- New service / subprocess
- **New write surface** (any new file path the project writes to, even one file under an existing dir)
- **New read surface** (any new external file or API the project reads from)
- New convention (naming, config layout, file location)

If yes: update `architecture.md` to reflect the new state (Data Flow section for surfaces; State / Component / Convention sections for the rest), AND pass `--architecture-impact component|data-flow|convention` flag to `write_decision_log.py` in F3.

### F3: Decision Log (ADR — decision-drop)

Iterate runs do NOT append to `decision_log.md` directly — two parallel
iterates would each compute `max(ADR)+1` in their own worktree and collide
on the number. Write a decision-DROP keyed by `run_id`; the sequential
`ADR-NNN` is assigned at exactly one serialized point —
`/shipwright-changelog` release time (`aggregate_decisions.py`):

```bash
uv run "{shared_root}/scripts/tools/write_decision_drop.py" \
  --project-root "{project_root}" \
  --run-id "{run_id}" \
  --section "Iterate — {type}: {short_description}" \
  --title "{short title}" \
  --context "{why}" --decision "{what}" --consequences "{impact}" \
  --rationale "{reasoning}" --rejected "{alternatives}" \
  [--architecture-impact component|data-flow|convention] \
  [--spec-ref ".shipwright/planning/adr/<NNN>-<slug>.md"]
```

The ADR's identity for this run is the **run_id** — there is no `ADR-NNN`
yet. F5c and F7 record `run_id` as the `adr` value; the finalization
verifier accepts run-id ADR identity and resolves it (decision-drop now,
`Run-ID:` line in `decision_log.md` post-aggregation). Reference the iterate
spec and run_id in the ADR body fields.

**Length budget — hard-rejected at write time (Iterate A.3, 2026-05-21).** Each field — `--context`, `--decision`, `--consequences`, `--rationale`, `--rejected` — MUST be **1-3 sentences, max 500 characters**. `decision_log.md` is always-loaded Layer-1 context: every verbose ADR pays for itself in tokens on every future iterate run. The tool now exits non-zero on overflow; the error message lists every offender and points at the spec-folder convention. Existing bloated entries are NOT retroactively rewritten — the gate is forward-only.

**ADR spec folder** for prose that overflows the budget: `.shipwright/planning/adr/<NNN>-<slug>.md` (flat, one file per ADR, ADR-number prefix gives collision protection). Pass the relative path via `--spec-ref`; the aggregator renders it as a `**Details:** [<filename>](../planning/adr/...)` bullet under the ADR row and rebuilds `.shipwright/planning/adr/INDEX.md` after each release pass.

`--spec-ref` is **mandatory** when:

- a field would otherwise exceed 500 characters (move the long prose into the spec file and keep the ADR body terse), or
- the decision references >3 alternatives, ADR-spanning diagrams, or non-trivial follow-up acceptance criteria — anything a future reader would otherwise have to reconstruct from commits.

Example (short ADR pointing at a long-form spec):

```bash
uv run "{shared_root}/scripts/tools/write_decision_drop.py" \
  --project-root "{project_root}" --run-id "{run_id}" \
  --section "Iterate — change: replay snapshot" \
  --title "Snapshot-from-mirror precedence" \
  --context "Live mirror often beats disk fallback; explain why in spec." \
  --decision "Try mirror first, then disk; never both." \
  --consequences "One round-trip per attach; deterministic blank fallback." \
  --architecture-impact component \
  --spec-ref ".shipwright/planning/adr/092-replay-snapshot.md"
```

### F3a: Reflection — Capture Learnings

Apply the reflection protocol (`references/reflection.md`):

1. Review the work done in this iterate run
2. Check: new patterns, gotchas, corrections, tool/infra insights?
3. **Decisions** → ADR with `--architecture-impact convention` (handled via F3 if applicable)
4. **Observations** → append to `.shipwright/agent_docs/conventions.md` under `## Learnings`
5. **Cross-project insights** → save Claude Code feedback/project Memory
6. If no learnings: skip — do not force entries

### F4: Record changelog entry (drop-directory)

Write one bullet per acceptance-criteria-level change via the drop tool:

```bash
uv run "{shared_root}/scripts/tools/write_changelog_drop.py" \
  --project-root "{project_root}" \
  --run-id "{run_id}" \
  --category "{Added|Changed|Deprecated|Removed|Fixed|Security}" \
  --bullet "Short description of the change (no leading '- ')"
```

Category mapping: `feat` → **Added**, `fix` → **Fixed**, `refactor` →
**Changed**. Multiple F4 calls per iterate are supported — each produces
its own `<run_id>_<NNN>.md` file under
`CHANGELOG-unreleased.d/<category>/`, so two feat bullets in the same
run don't overwrite each other.

Files produced here are aggregated into `CHANGELOG.md` at release time
by `/shipwright-changelog` via `aggregate_changelog.py`. Do NOT append
directly to `CHANGELOG.md [Unreleased]` — the split-brain between drop
files and legacy inline bullets is flagged by a release-time WARN but
can still obscure an operator-level merge decision.

Stage the generated drop files for inclusion in commit:
```bash
git add CHANGELOG-unreleased.d/
```

### F5: Write Test Results JSON

Write latest-run state to `shipwright_test_results.json`:
```json
{
  "iterate_latest": {
    "run_id": "{run_id}",
    "date": "{YYYY-MM-DD}",
    "unit": { "status": "passed|failed|not_run", "passed": N, "total": N },
    "integration": { "status": "passed|failed|skipped|not_run", "passed": N, "total": N },
    "pgtap": { "status": "passed|failed|skipped|not_run", "passed": N, "total": N },
    "e2e": { "status": "passed|partial|skipped|not_run", "passed": N, "total": N },
    "design_fidelity": { "status": "passed|partial|skipped|not_run", "passed": N, "total": N },
    "smoke": { "status": "passed|skipped|not_run" },
    "degraded": []
  }
}
```

> **Why the next steps run BEFORE the commit (F6):** the finalization script
> and the `iterate_history` append write artifact files tracked in the repo.
> Running them after F6 would dirty the working tree immediately after
> committing and force a `git commit --amend` — which conflicts with the
> "never amend" rule in the global `CLAUDE.md`.

### F5b: Finalize Iterate Artifacts

Run **one** script that handles compliance, dashboard, and handoff:

```bash
uv run "{shared_root}/scripts/tools/finalize_iterate.py" \
  --project-root "{project_root}" \
  --run-id "{run_id}" \
  --reason "iterate: {short_description}"
```

This replaces the former F5a (compliance), F5b (dashboard), and F11 (handoff)
as a single deterministic step. The script is idempotent — safe to run
multiple times. If you skip this step, the Stop hook will run it
automatically as a fallback when the session ends.

> **Note:** F7 (event recording with commit SHA) still runs separately
> after F6 because it needs the commit hash that F6 produces.

### F5c: Record iterate entry (file-per-iterate)

Run **one script** that writes the entry file, handles legacy-array
migration (if this project still carries an `iterate_history` array in
`shipwright_run_config.json`), enforces retention, and records any
quarantined legacy rows for operator review:

```bash
uv run "{shared_root}/scripts/tools/append_iterate_entry.py" \
  --project-root "{project_root}" \
  --run-id "{run_id}" \
  --entry-json '{
    "type": "{feature|change|bug}",
    "complexity": "{trivial|small|medium|large}",
    "branch": "iterate/{short-description}",
    "spec": "{path to iterate spec or null}",
    "tests_passed": true,
    "adr": "{run_id}"
  }'
```

Writes: `.shipwright/agent_docs/iterates/<run_id>.json` (atomic, under file lock
covering the full append transaction). `run_id` and `date` are added by
the tool itself (canonical ISO-8601 UTC `...Z` form) — do NOT set them
in `--entry-json`.

On first call against a project with a legacy `iterate_history` array,
the tool migrates every row into its own file; invalid or duplicate
legacy rows land in `.shipwright/agent_docs/iterates/_quarantine/` and the count is
recorded on run config as `_iterate_migration_quarantined_count` so the
handoff + verifiers surface it.

Retention: keep the 50 most recent entry files per project (sorted by
ISO date, run_id tiebreaker). Older entries preserved in
`shipwright_events.jsonl`.

Note: the commit hash is intentionally NOT stored here. Look it up in
`shipwright_events.jsonl` by `run_id` (F7 records the real commit hash
there). This omission is what lets F5c run pre-commit in a single
atomic F6.

### F6: Commit (Conventional Commits)

- **Feature:** `feat({scope}): {description}`
- **Change:** `refactor({scope}): {description}` or `feat` if user-facing
- **Bug:** `fix({scope}): {description}`

By this point F3, F3a, F4, F5, F5a, F5b, and F5c have all written their
artifacts into the working tree. Stage everything explicitly rather than
using `git add -A` (avoids accidentally picking up unrelated dirty files):

```bash
# Code + tests (run-specific paths)
git add <source files edited in build>
git add <test files added/modified in build>

# Finalization artifacts (always)
git add {project_root}/CHANGELOG-unreleased.d/       # F4 drop files (one or more)
git add {project_root}/.shipwright/agent_docs/decision-drops/        # F3 decision-drop (one or more)
git add {project_root}/.shipwright/agent_docs/build_dashboard.md
git add {project_root}/.shipwright/agent_docs/iterates/          # F5c entry + any migration quarantine
git add {project_root}/shipwright_test_results.json
git add {project_root}/shipwright_run_config.json

# Conditional finalization artifacts
git add {project_root}/.shipwright/agent_docs/conventions.md       # if F3a wrote learnings
git add {project_root}/.shipwright/agent_docs/architecture.md      # if F2 flagged structural impact
git add {project_root}/.shipwright/planning/**/spec.md             # if F1 flagged drift
git add {project_root}/.shipwright/planning/iterate/*.md           # if medium+ (iterate spec / mini-plan)

# Compliance artifacts (if the project tracks .shipwright/compliance/)
git add {project_root}/.shipwright/compliance/

git commit -m "<type>(<scope>): <description>

<body>

Run-ID: {run_id}
Co-Authored-By: Claude <noreply@anthropic.com>"
```

If a path in the list above doesn't exist in the current project, skip that
`git add` — it just means that particular artifact wasn't touched by this run.
Never add `-A` to bypass the list.

### F7: Record Event

F7 is the only finalization step that requires the new commit hash. It writes
only to `shipwright_events.jsonl` (gitignored in every Shipwright profile),
so running it post-commit produces no tracked-file drift.

```bash
# Compute changed_files for the new commit (vs the merge base) so D's
# boundary drift detection (`is_io_boundary_change`) and HIGH-5's
# round-trip heuristic scoping have a real list to consume.
# E spec MEDIUM-D1: every work_completed event SHOULD record this field.
prev=$(git merge-base HEAD "$(git symbolic-ref refs/remotes/origin/HEAD 2>/dev/null | sed 's@^refs/remotes/origin/@@' || echo main)")
changed=$(git diff --name-only "${prev}..HEAD" | tr '\n' ',' | sed 's/,$//')

uv run "{shared_root}/scripts/tools/record_event.py" \
  --project-root "{project_root}" \
  --type work_completed --source iterate \
  --intent {feature|change|bug} \
  --description "{short_description}" \
  --commit "$(git rev-parse HEAD)" \
  --changed-files "${changed}" \
  --spec-impact {add|modify|remove|none} \
  --affected-frs "{FR IDs from Step 2 — ADD ∪ MODIFY ∪ REMOVE}" \
  --new-frs "{FR IDs from Step 2 — ADD only}" \
  --tests-passed {N} --tests-total {N} \
  --e2e-run {true|false} \
  --adr-id "{run_id}" \
  --deduplicate-by-commit
```

> **Spec-impact arguments are DERIVED from Step 2, not invented here.**
> `--spec-impact` is the Step 2 classification; `--affected-frs` /
> `--new-frs` are the FR IDs Step 2 touched. For a FEATURE/CHANGE iterate,
> `record_event.py` exits 1 (nothing written) unless either `--affected-frs`
> / `--new-frs` is non-empty OR `--spec-impact none` is paired with
> `--spec-impact-justification "..."`. BUG iterates may omit all three.
> Use `--spec-impact none --spec-impact-justification "..."` for a
> behavior-preserving refactor that genuinely touches no FR.

### F11: Push Branch, Open PR & Verify

**Leak-guard first** — confirm the run never touched the main repo working
tree (snapshot-and-diff against the B1a Step-1 snapshot):
```bash
uv run "{shared_root}/scripts/checks/check_iterate_isolation.py" \
  --project-root "{project_root}" --run-id "{run_id}" --stage f11
```
Non-zero exit = **STOP**.

**Push the iterate branch and open a PR.** An iterate run NEVER checks out,
merges, or pushes the default branch — that races every other parallel
iterate. One iterate = one branch = one PR.
```bash
default_branch=$(git -C "{project_root}" symbolic-ref refs/remotes/origin/HEAD 2>/dev/null | sed 's@^refs/remotes/origin/@@' || echo main)
git -C "{project_root}" push -u origin "iterate/{slug}"
# gh has no `-C` analog — it acts on the cwd's repo. cd into the worktree
# so gh can never operate on the main repo even if the shell cwd drifted.
cd "{project_root}"
gh pr create --base "$default_branch" --head "iterate/{slug}" \
  --title "<type>(<scope>): <description>" \
  --body "<summary>

Run-ID: {run_id}"
```
If `iterate/{slug}` has diverged from `origin/<default>` since B1a fetched it
(another iterate merged meanwhile), rebase onto current `origin/<default>`
and resolve conflicts BEFORE `gh pr create` — that rebase is the deliberate,
single conflict point. The PR is then left **open for review**: this run
STOPS here. Merging the PR is a separate, human-gated step.

**Update session handoff** to reflect completed state. Pass `--reason`
so the handoff shows what caused the regeneration instead of the default
`context compaction`:
```bash
uv run "{shared_root}/scripts/tools/generate_session_handoff.py" \
  --project-root "{project_root}" \
  --reason "iterate completion: {run_id}"
```

**Gate check:** F7 (Record Event) writes the `work_completed` event into
the worktree-aware-resolved event log — the MAIN repo's
`shipwright_events.jsonl`, not the worktree copy (see
`events_log.resolve_events_path`). The deterministic verifier below checks
this authoritatively via `check_events_has_commit` (also worktree-aware), so
no separate grep is needed. A literal
`grep "{project_root}/shipwright_events.jsonl"` would false-negative — that
worktree path is not where F7 writes.

**Deterministic verifier.** After the gate check, run the finalization
verifier and fail the iterate run on red:
```bash
uv run "{shared_root}/scripts/tools/verify_iterate_finalization.py" \
  --run-id "{run_id}" \
  --project-root "{project_root}" \
  --commit "$(git -C "{project_root}" rev-parse HEAD)"
```
Exit 0 = green (or warnings only), exit 1 = at least one required
artifact missing. Add `--strict` to treat warnings as errors.

### F12: Release Prompt

After opening the PR, count the pending changelog drop files — `*.md` under
`{project_root}/CHANGELOG-unreleased.d/` (excluding `.gitkeep`). If > 0:

> "{N} unreleased changelog drop(s) pending. Once this PR merges, run
> /shipwright-changelog — it aggregates the changelog drops + the ADR
> decision-drops and tags the release."

`/shipwright-changelog` runs against the default branch AFTER the PR
merges, not now — the drops are not on `origin/<default>` yet.

Print summary:
```
================================================================================
SHIPWRIGHT-ITERATE COMPLETE
================================================================================
Run ID:     {run_id}
Type:       {FEATURE | CHANGE | BUG}
Complexity: {level}
Worktree:   .worktrees/{slug}/
Branch:     iterate/{slug}
Commit:     {hash}
Tests:      {N} passing (unit: {N}, e2e: {N|skipped}, design_fidelity: {N|skipped})
Specs:      {iterate spec path | FR update only | no changes}
ADR:        decision-drop {run_id} (ADR-NNN assigned at changelog release)
CHANGELOG:  drop file(s) under CHANGELOG-unreleased.d/
Compliance: Updated
PR:         {pr_url} — open for review
================================================================================
```

---

## Degraded Mode

When metadata is incomplete:
- **No sync config:** default to medium complexity, run full test suite
- **Stale mappings:** note in summary, conservative defaults
- **No visual-guidelines.md:** skip design check, note in ADR
- **Browser verify fails to start:** fall back to test-only verification
- **Code-reviewer unavailable:** self-review only, flag in ADR as "review-limited"
- **review.py unavailable / no API key + user chose skip:** Branch B Option 2 — fall back to the mandatory self-review that already ran, log the opt-out (with reason) in the iterate ADR, write `external_review_state.json` marker with `status: skipped_user_opt_out`
- **Pipeline handoff fails:** print manual instructions + handoff file path
- **No .shipwright/designs/screens/:** skip mockup comparison in design fidelity check, design_fidelity marked "degraded", note in ADR

Record all degraded conditions in `shipwright_test_results.json` → `degraded` array.

---

## Error Handling

### Test Failures
1. Root cause investigation — read error output, identify failing component
2. Pattern analysis — same root cause as last attempt? Change approach
3. Hypothesis — state what you'll fix and why before changing code
4. Fix and verify — targeted fix, then re-run tests
5. If stuck after 3 attempts: escalate to user

### Pre-commit Hook Failures
- Linting failures: auto-fix and re-commit
- Type errors: fix and re-commit
- Never bypass hooks with `--no-verify`

### Missing Sync Config
- Skip FR mapping (affected_frs = TBD)
- Skip drift check in finalization
- Default to medium complexity (conservative)

### Session Handoff
If context pressure detected during medium+ changes, see `references/iteration-reviews.md` for handoff protocol.
