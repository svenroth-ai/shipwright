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
Repo Scout, Mini-Plan, Escape Hatch  → references/iteration-planning.md
Self-Review, Full Review, Handoff     → references/iteration-reviews.md
Design Check, Testing, Visual, E2E    → references/design-and-testing.md
Reflection Protocol                   → references/reflection.md
Risk Taxonomy, Override Classes       → this file (inline)
Phase Matrix                          → this file (Section 6, NORMATIVE)
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

### B1. Check for In-Progress Iterate Run

Before starting fresh, check if a previous iterate run was interrupted:

1. Enumerate + classify existing `iterate/*` branches via the
   dedicated helper (read-only; exits 1 only on hard git failures):
   ```bash
   uv run {shared_root}/scripts/tools/list_iterate_branches.py --project-root . --main "$DEFAULT_BRANCH"
   ```
   The JSON output (schema v1) has per-branch metadata plus
   backward-compat arrays `active` / `stale` / `locked`. Use the
   `active` list for the resume-candidate menu. For every branch in
   `stale`, print a one-line housekeeping hint:
   `stale iterate branch iterate/X found; run "git branch -D iterate/X" to remove`.
   For every branch in `locked`, print:
   `iterate/X locked in worktree <path>; continue there or kill the other worktree first`.

   Known limitations (surfaced in the helper output `errors[]`):
   - Squash-merged branches stay in `active` until manual `git branch -D`;
     the helper cannot reliably detect them locally.
   - Both `main` AND `master` present without `--main` → `main: null`
     + ambiguity error. Pass `--main <name>` explicitly.
2. Check if `.shipwright/agent_docs/session_handoff.md` exists and references an iterate run_id
3. Check current git branch — if already on an `iterate/` branch
4. **Worktree self-exclusion:** if running inside a secondary worktree
   (`git rev-parse --show-toplevel` differs from the main repo path), exclude the
   current branch from the candidate list — otherwise B1 would always offer
   "Parallel" on the current branch, creating an infinite loop.

**If an in-progress run is detected (any of 1–3 matches after filtering):**

```
================================================================================
SHIPWRIGHT-ITERATE: Previous Run Detected
================================================================================
Run ID:     {run_id from handoff or branch name}
Branch:     {branch name}
Phase:      {last phase from handoff, or "unknown"}
Files:      {modified files count from git status}

Options:
  1. Resume   — continue from where we left off
  2. Abandon  — discard and start fresh (branch will be deleted)
  3. Complete — skip to finalization (F1-F11)
  4. Parallel — start different work alongside the current run
                (new worktree, current run stays untouched)

Decision guide:
  - Continue the same topic?           → Resume
  - Completely different topic now?    → Parallel
  - Discard current and start over?    → Abandon
  - Finalize the current run?          → Complete
================================================================================
```

**Wait for user choice.**

- **Resume:** Read `.shipwright/agent_docs/session_handoff.md` for full state (completed phases, remaining work, test status, blocked items). Skip Steps C-G (Run ID, Intent, Complexity, Summary, Interview). Reuse the existing run_id, branch, and iterate spec.

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
- **Abandon:** Delete the iterate branch (`git branch -D iterate/{name}`), remove `.shipwright/agent_docs/session_handoff.md`, proceed with fresh run from Step B2.
- **Complete:** Read handoff for context, skip to Finalization (F1-F11) to commit, record event, and merge what's already been built. **Same replay check applies** — run External Review / Self-Review first if markers are missing, before F1.
- **Parallel:** Leave the detected run completely untouched. Exit this session with status `parallel_setup` (not `abandoned` or `failed` — no work is lost). Print the worktree setup commands below and stop. The new iterate is started in a **new Claude Code session inside the worktree**, not in this session.

  ```bash
  # Resolve default branch dynamically (do NOT hardcode `main`):
  DEFAULT_BRANCH=$(git symbolic-ref --short refs/remotes/origin/HEAD 2>/dev/null | sed 's@^origin/@@' || echo main)

  # Precondition checks — refuse if worktree/branch already exists:
  git worktree list | grep -q ".worktrees/<slug>" && { echo "Worktree already exists"; exit 1; }
  git branch --list iterate/<slug> | grep -q . && { echo "Branch already exists — pick a different slug or clean up first"; exit 1; }

  # Create worktree inside repo (so .gitignore applies):
  git worktree add .worktrees/<slug> -b iterate/<slug> "$DEFAULT_BRANCH"
  cd .worktrees/<slug>

  # Re-hydrate dependencies + env — worktrees copy neither node_modules nor .env files.
  # Emit ONLY the lines whose precondition matches the target project's shape:
  [ -f ../../.env.local ]          && cp ../../.env.local .env.local
  [ -f ../../.env ]                && cp ../../.env .env
  [ -f package.json ]              && npm install
  [ -f webui/package.json ]        && (cd webui && npm install)
  [ -f webui/client/package.json ] && (cd webui/client && npm install)
  [ -f webui/server/package.json ] && (cd webui/server && npm install)
  [ -f client/package.json ]       && (cd client && npm install)
  [ -f pyproject.toml ]            && uv sync

  # Then: open a new Claude Code session in .worktrees/<slug> and run /shipwright-iterate fresh.
  ```

  **Skill guidance:** probe file existence before emitting each install line — print only what applies to the target project's shape. A Python-only project should not see `npm install`, a repo without `webui/` should not see the webui lines.

**If no in-progress run detected:** Continue to B2 normally.

### B1a. Parallel Iterate Conventions

These rules apply to the **Parallel** option in B1 and to any manual worktree-based parallel iterate work. They keep PRs independent and avoid merge conflicts.

- **Branch base:** always the project's default branch (resolved via `git symbolic-ref refs/remotes/origin/HEAD`, fallback `main`). **Never** branch from another `iterate/*` — chains iterates and muddles the PR/changelog.
- **Worktree path:** `.worktrees/<slug>` **inside the repo** (hidden folder, `.gitignore`'d). Verify with `git check-ignore .worktrees/`.
- **Worktree init:** git-worktrees do NOT carry `node_modules` or `.env*`. The Parallel setup snippet above copies env files and runs the project's install commands — adapt for the project shape.
- **Disjoint file scopes:** if two iterates touch the same file, serialize rather than parallelize. Overlap = manual merge conflicts.
- **Dev server:** default is one at a time. Parallel worktrees require explicit port overrides (e.g. `PORT` for Hono + `VITE_PORT` for Vite in the Shipwright webui). Use intentionally, not as a default.
- **One PR per iterate, one changelog entry per iterate.** Conventional-Commit sort is merge-order-independent. Rebase per PR is expected when multiple are open against the default branch.
- **WARNING — race on adopted target projects:** on any project with `shipwright_run_config.json`, parallel iterates produce a merge conflict in `iterate_history[]`. Use this workflow today only if manual conflict resolution is acceptable. Structural fix tracked as `iterate-history-file-per-iterate` (must land before `/shipwright-adopt` on the shipwright monorepo itself).
- **WARNING — CHANGELOG.md `[Unreleased]` is a merge hotspot today.** F4 appends to `[Unreleased]` for every iterate. Two parallel iterates conflict on merge — the second PR must rebase and resolve the bullet merge manually. Structural fix bundled with the iterate_history refactor as a `CHANGELOG-unreleased.d/` drop pattern.
- **Cleanup:** `git worktree remove .worktrees/<slug>` removes the worktree but **not** the branch. After PR merge: also `git branch -D iterate/<slug>`. Use the helper (`uv run {shared_root}/scripts/tools/list_iterate_branches.py`) to see which branches are in `locked` (active in another worktree) vs `stale` (safe to delete).

See also: `docs/guide.md` chapter "Parallel Development with Worktrees" for the full walkthrough.

### B2. Load Project Context (MANDATORY)

**Read ALL of these files NOW before proceeding.** This context is required for accurate intent classification, complexity assessment, and interview questions. Do NOT skip this step.

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

Generate `run_id`: `iterate-{YYYYMMDD}-{short-description}`
Example: `iterate-20260405-course-search`

This ID is propagated through ALL artifacts: iterate spec, mini-plan, ADR, event log, iterate_history, session handoff.

### D. Determine Intent Type

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

### E. Assess Complexity (Two-Stage)

#### Stage 1: Quick Estimate

```bash
uv run {plugin_root}/scripts/lib/classify_complexity.py \
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

Note: "touches_db" (ordinary query/model edits without schema changes) is NOT a risk flag.

---

## Override Classes

| Category | Phases | User can skip? |
|---|---|---|
| **Mandatory** | Self-review, unit test, commit, ADR, compliance, test results JSON, iterate_history | Never skippable |
| **Safety-enforced** | Full review (when risk flags), full test suite (when shared infra), down.sql (when migrations) | Only with explicit risk acknowledgment |
| **Advisory** | Design check, mini-plan, design fidelity, E2E update, external LLM review, release prompt | Freely skippable |
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

## Affected FRs
- {FR-XX.YY}: {what changes or is added}

## Out of Scope
- {from interview answer — what explicitly will NOT be done}

## Design Notes
{Filled during Design Check. Include:
 - Affected mockup files from .shipwright/designs/screens/ (e.g. "10-kanban-board.html")
 - Design tokens applied (colors, spacing, typography)
 - New vs modified components
 - Deviations from visual guidelines with justification}
```

### Step 2: Spec Update (always)
1. Identify which spec file(s) cover the affected area
2. **Append** a new FR entry to the appropriate spec section
3. If `shipwright_sync_config.json` exists, add mappings for new files

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
1. Create feature branch `iterate/{short-description}` **branched from the project's default branch** (resolved via `git symbolic-ref refs/remotes/origin/HEAD`, fallback `main`). Never from another `iterate/*` branch — chains iterates and muddles the PR/changelog. See B1a for parallel-iterate conventions.
2. **RED — Write failing tests first**, at minimum one test per Acceptance Criteria:
   - Tests assert on **outcomes, not internal state**
   - At least one **happy-path AND one error-path** test per AC
   - **User interactions:** onClick/onSubmit/onChange triggers the expected action (not just "renders without error")
   - **Form submissions:** input → submit → API/DB call is invoked with correct data
   - **API calls:** correct endpoint, correct parameters, error case handled
   - **Data persistence:** create/update/delete triggers the correct DB/API call
   - No tests that always pass regardless of implementation
3. Run tests — they **MUST fail** (if they pass: you're testing the wrong thing or it's already implemented)
4. **GREEN — Implement** minimum code until tests pass
5. Run tests after each significant change
6. **Verify wiring** — would the test fail if the wiring (onClick → handler → API) is missing? If not: improve the test
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
See `references/iteration-reviews.md` for 6-point checklist.

### Step 8: Full Code Review (conditional)
See `references/iteration-reviews.md` for trigger rules.

### Step 9: Browser Verify + Smoke Test (if UI)
See `references/design-and-testing.md`.

### Step 10: Testing
- Trivial/small: `npx vitest --related $(git diff --name-only HEAD) --run`
- Medium+: `npx vitest run` (full suite)
- Safety floor paths → always full suite
See `references/design-and-testing.md` for details.

### Step 11: E2E Update (features that change user-visible behavior + medium+ changes with new flows)
See `references/design-and-testing.md`.

### Step 12: Design Fidelity (if structural UI)
See `references/design-and-testing.md` for structural extraction + agent deep analysis protocol.

### Step 13: Escalation Check
See Section 7 (Mid-Flight Escalation).

### Step 14: Finalize
Go to **Finalization** below.

---

## Path B: CHANGE (modify existing behavior)

Same steps as FEATURE, with these differences:
- Step 2: **Update** existing FR entry instead of appending new one
- Step 6: Update existing tests to reflect new expected behavior, then implement

---

## Path C: BUG (fix something broken)

### Step 1: Iterate Spec (medium+ only)
Same as FEATURE Step 1.

### Step 2: Spec Update (only if spec was wrong or behavior changes)
Check if the spec itself was incorrect. If yes, update. If no, skip.

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
1. Create feature branch `iterate/fix-{short-description}` **branched from the project's default branch** (resolved via `git symbolic-ref refs/remotes/origin/HEAD`, fallback `main`). Never from another `iterate/*` branch — chains iterates and muddles the PR/changelog. See B1a for parallel-iterate conventions.
2. **Fix the root cause** — targeted change, minimal scope. Do not fix symptoms.
3. Run reproducing test to verify it passes
4. Run related tests to verify no regressions

### Step 6-14: Same as FEATURE (self-review, code review, testing, escalation, finalize)
Follow the Phase Matrix to determine which steps run for the assessed complexity.

---

## 5b. Campaign Mode (Autonomous Multi-Iterate)

When invoked with `--campaign <slug>` and `--autonomous`, run multiple sub-iterates sequentially without manual gates. This formalizes the ad-hoc orchestration pattern used in iterate 14.

**Flags:** `/shipwright-iterate --campaign <slug> [--autonomous]`

### Campaign Setup (interactive, once)

If campaign directory doesn't exist yet:

1. User describes the overarching goal
2. Together, decompose into sub-iterates (each should be trivial–medium complexity)
3. Initialize campaign structure:
```bash
uv run {plugin_root}/scripts/tools/campaign_init.py \
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
uv run {plugin_root}/scripts/tools/campaign_progress.py list-units \
  --campaign-dir ".shipwright/planning/iterate/campaigns/{slug}" > /tmp/campaign_units.json

uv run {shared_root}/scripts/lib/autonomous_loop.py init \
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
    uv run {plugin_root}/scripts/tools/campaign_progress.py update-status \
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
| Spec Update (existing FRs) | always (BUG: only if spec wrong) | always (BUG: only if spec wrong) | always (BUG: only if spec wrong) | — |
| Mini-Plan | skip | FEATURE only | yes + alternative (all types) | — |
| User Approval | skip | skip | before build | — |
| External LLM Review | skip | skip | auto | — |
| Design Check | skip | Tier 1 (text) | Tier 2 (markdown) | — |
| Build (TDD) | always | always | always | — |
| Self-Review | always | always | always | — |
| Full Code Review | only if risk flags | only if risk flags | always | — |
| Browser Verify | if UI | if UI | if UI | — |
| Smoke Test | if server up | if server up | if server up | — |
| Unit Test | `--related` | `--related` | full suite | — |
| Integration Test | if CRUD | if CRUD | full suite | — |
| pgTAP DB Test | if new RLS | if new RLS | full suite | — |
| E2E Update | if feature+UI | if feature+UI | always | — |
| Design Fidelity | skip | if structural UI | if UI | — |
| architecture.md | if structural impact | if structural impact | if structural impact | — |
| Test Results JSON | always | always | always | — |
| run_config iterate_history | always | always | always | — |
| Session Handoff | skip | if needed | if needed | — |
| Release Prompt | always | always | always | — |

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
| **Iterate spec** (`.shipwright/planning/iterate/`) | Intent, ACs, scope, out-of-scope | Rationale (→ ADR), structure (→ architecture) |
| **spec.md** (existing FRs) | Normative FR changes | Why (→ ADR), approach (→ mini-plan) |
| **ADR** (`decision_log.md`) | Rationale, alternatives, consequences | Full ACs (→ spec), structure (→ architecture) |
| **architecture.md** | Current structural state | Decisions (→ ADR), requirements (→ spec) |
| **Mini-plan** (`.shipwright/planning/iterate/`) | Approach, files, test strategy | Requirements (→ spec), decisions (→ ADR) |

---

## Finalization (all paths)

**CRITICAL: Steps F0–F11 (including F3a, F5a, F5b, F5c) are MANDATORY. Do NOT skip any step.**

> **Order matters.** F3/F3a/F4/F5/F5a/F5b/F5c all write tracked artifacts and MUST run before F6 so a single atomic commit stages them. F7 is the only step that legitimately runs after F6 (it needs the commit hash and writes only to a gitignored event log). Do not reorder.

### F0: Fresh Verification Gate

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

### F1: Drift Check

```bash
uv run {shared_root}/scripts/artifact_sync.py \
  --project-root "{project_root}" --ref "HEAD~1..HEAD"
```

If drift detected, update specs. If iterate spec exists (medium+), check off completed ACs and update status to `implemented`.

### F2: Architecture Update (conditional)

Check: "Did I add a new route, component, schema, service, or data flow?"
If yes: pass `--architecture-impact component|data-flow|convention` flag to `write_decision_log.py` in F3.

### F3: Decision Log (ADR)

```bash
uv run {shared_root}/scripts/tools/write_decision_log.py \
  --section "Iterate — {type}: {short_description}" \
  --commit "$(git rev-parse HEAD)" \
  --title "{short title}" \
  --context "{why}" --decision "{what}" --consequences "{impact}" \
  --rationale "{reasoning}" --rejected "{alternatives}" \
  --project-root "{project_root}"
```

Reference iterate spec and run_id in the ADR body.

**Length budget (forward-only, applies to new ADRs).** Each field — `--context`, `--decision`, `--consequences`, `--rationale`, `--rejected` — should be **1-3 sentences, max ~500 characters**. `decision_log.md` is always-loaded Layer-1 context: every new iterate run pays for every verbose ADR in tokens. Keep entries self-contained but terse. Include rationale only if the decision isn't self-explanatory. `write_decision_log.py` will print a non-blocking stderr warning if a field exceeds 500 characters; it will still append the entry. Do NOT retroactively shorten existing ADRs — git churn for historical detail isn't worth it.

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
uv run {shared_root}/scripts/tools/write_changelog_drop.py \
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
uv run {shared_root}/scripts/tools/finalize_iterate.py \
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
uv run {shared_root}/scripts/tools/append_iterate_entry.py \
  --project-root "{project_root}" \
  --run-id "{run_id}" \
  --entry-json '{
    "type": "{feature|change|bug}",
    "complexity": "{trivial|small|medium|large}",
    "branch": "iterate/{short-description}",
    "spec": "{path to iterate spec or null}",
    "tests_passed": true,
    "adr": "{ADR-NNN or null}"
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
git add {project_root}/.shipwright/agent_docs/decision_log.md
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
uv run {shared_root}/scripts/tools/record_event.py \
  --project-root "{project_root}" \
  --type work_completed --source iterate \
  --intent {feature|change|bug} \
  --description "{short_description}" \
  --commit "$(git rev-parse HEAD)" \
  --affected-frs "{comma_separated_FRs}" \
  --tests-passed {N} --tests-total {N} \
  --e2e-run {true|false} \
  --adr-id "ADR-{NNN}" \
  --deduplicate-by-commit
```

### F11: Merge, Push & Verify

```bash
main_branch=$(git symbolic-ref refs/remotes/origin/HEAD 2>/dev/null | sed 's@^refs/remotes/origin/@@' || echo "master")
git checkout "$main_branch"
git merge iterate/{short-description}
git push origin "$main_branch"
```

**Update session handoff** to reflect completed state. Pass `--reason`
so the handoff shows what caused the regeneration instead of the default
`context compaction` (iterate 11.3):
```bash
uv run {shared_root}/scripts/tools/generate_session_handoff.py \
  --project-root "{project_root}" \
  --reason "iterate completion: {run_id}"
```

**Gate check:** Verify F7 (Record Event) was executed:
```bash
grep "$(git rev-parse HEAD)" "{project_root}/shipwright_events.jsonl" > /dev/null 2>&1
```

**Iterate 11 — deterministic verifier.** After the gate check, run the
finalization verifier and fail the iterate run on red:
```bash
uv run {shared_root}/scripts/tools/verify_iterate_finalization.py \
  --run-id "{run_id}" \
  --project-root "{project_root}" \
  --commit "$(git rev-parse HEAD)"
```
Exit 0 = green (or warnings only), exit 1 = at least one required
artifact missing. Add `--strict` to treat warnings as errors.

### F12: Release Prompt

After pushing to main, check if `CHANGELOG.md` has entries under `[Unreleased]`:

Count the `- ` lines between `## [Unreleased]` and the next `## [v` heading. If > 0:

> "{N} unreleased changelog entries found. Run /shipwright-changelog to tag a release?"

- If **yes**: invoke `/shipwright-changelog` (handles version bump, tagging, push — respects project autonomy mode)
- If **no**: proceed to summary (entries stay under `[Unreleased]`)

Print summary:
```
================================================================================
SHIPWRIGHT-ITERATE COMPLETE
================================================================================
Run ID:     {run_id}
Type:       {FEATURE | CHANGE | BUG}
Complexity: {level}
Branch:     iterate/{short-description}
Commit:     {hash}
Tests:      {N} passing (unit: {N}, e2e: {N|skipped}, design_fidelity: {N|skipped})
Specs:      {iterate spec path | FR update only | no changes}
ADR:        Logged in decision_log.md
CHANGELOG:  Updated ([Unreleased])
Release:    {version tag | "deferred (N unreleased entries)"}
Compliance: Updated
Merged:     {main_branch} ← iterate/{short-description}
Pushed:     origin/{main_branch}
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
