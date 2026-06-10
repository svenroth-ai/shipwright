---
name: shipwright-iterate
description: "Lightweight SDLC for ongoing changes in completed Shipwright projects.\nTRIGGER when: user asks to add a feature, fix a bug, change behavior, refactor, update, modify, or improve code in a project that has shipwright_run_config.json with status complete. Also when user describes a bug report, enhancement request, or any code-level change to a finished project.\nDO NOT TRIGGER when: user asks about project setup (/shipwright-project), planning (/shipwright-plan), initial build (/shipwright-build), deployment (/shipwright-deploy), running tests (/shipwright-test), or non-code tasks like documentation questions. Also DO NOT TRIGGER when the pipeline is still in_progress — those changes belong to the current pipeline phase."
license: MIT
compatibility: Requires uv (Python 3.11+), git repository required, completed Shipwright project
---

# Shipwright Iterate Skill v0.3.0

Complexity-adaptive change lifecycle for completed Shipwright projects. Detects intent (feature, change, bug), assesses complexity, runs the right amount of process.

> **How invoked:** directly via `/shipwright-iterate`, or via the `suggest_iterate.py` UserPromptSubmit hook context.
> **External review (v0.5.x+):** medium+ uses `{shared_root}/scripts/tools/external_review.py --mode iterate`, `check-external-review-keys.py`, `mark-review-state.py` (Branch A/B/C gate).

## Phase Index — Where the prose lives

| Section | Reference |
|---|---|
| Repo Scout, Mini-Plan | [iteration-planning](references/iteration-planning.md) · [escape-hatch](references/escape-hatch.md) |
| Self-Review, Full Review, Handoff | [iteration-reviews](references/iteration-reviews.md) |
| Design Check, Testing, Visual, E2E | [design-and-testing](references/design-and-testing.md) |
| Reflection, Boundary Probes, Round-Trip, Confidence | [reflection](references/reflection.md) · [boundary-probes](references/boundary-probes.md) · [round-trip-tests](references/round-trip-tests.md) · [confidence-anti-patterns](references/confidence-anti-patterns.md) |
| Context Loading | [context-loading](references/context-loading.md) |
| Path A / B / C body | [path-a-feature](references/path-a-feature.md) · [path-b-change](references/path-b-change.md) · [path-c-bug](references/path-c-bug.md) · [F-debug](references/F-debug.md) (BUG systematic-debugging) |
| Campaign Mode, Escalation, Degraded, Errors | [campaign-mode](references/campaign-mode.md) · [mid-flight-escalation](references/mid-flight-escalation.md) · [degraded-mode](references/degraded-mode.md) · [error-handling](references/error-handling.md) |
| Artifact Ownership | [artifact-ownership](references/artifact-ownership.md) |
| Finalization F-phases | [F0](references/F0.md) · [F0.5](references/F0.5.md) · [F1](references/F1.md) · [F2](references/F2.md) · [F3](references/F3.md) · [F3a](references/F3a.md) · [F4](references/F4.md) · [F5](references/F5.md) · [F5b](references/F5b.md) · [F5c](references/F5c.md) · [F6](references/F6.md) · [F6.5](references/F6.5.md) · [F7](references/F7.md) · [F7b](references/F7b.md) · [F11](references/F11.md) · [F12](references/F12.md) |
| Risk Taxonomy, Override Classes, Phase Matrix | this file (inline — NORMATIVE) |

---

## CRITICAL: First Actions

**Governing rules:** read and follow `shared/constitution.md` (ALWAYS / ASK FIRST / NEVER). **BEFORE any other tools:**

### A. Print Intro Banner

```
================================================================================
SHIPWRIGHT-ITERATE v0.3.0: Adaptive Change Lifecycle
================================================================================
Usage: /shipwright-iterate --type feature|change|bug "description"
   or: Auto-detected from your prompt (via hook context)
Paths: FEATURE / CHANGE → [interview]→[spec]→[plan]→[approval]→[review]→[design]→build→test→commit
       BUG              → [spec]→reproduce→[plan]→fix→test→commit
Complexity: trivial | small | medium | large (auto-detected, overridable)
================================================================================
```

### B. Validate Project

Verify `shipwright_run_config.json` exists with `status: "complete"` (or `iterate_history` exists). Otherwise print the "Completed Project Required" notice and **stop**.

### B1. Resumable Iterate Run

Every iterate runs in a worktree under `.worktrees/<slug>/`. If inside a worktree (`git rev-parse --git-common-dir` resolves above cwd), resume in place. Otherwise enumerate branches with `uv run "{shared_root}/scripts/tools/list_iterate_branches.py" --project-root .` (surfaces `locked` = resumable, `stale` = housekeeping). Check `.shipwright/agent_docs/session_handoff.md` for `run_id`. Offer Resume / Abandon / Complete. **Resume/Complete replay-check:** if medium+ has no external-review marker AND `feedback_iterations > 0`, run Step 4 first. If the iterate ADR has no `Self-Review:` block, run Step 7 before commit.

### B1a. Worktree Isolation (unconditional)

```bash
uv run "{shared_root}/scripts/tools/setup_iterate_worktree.py" \
  --project-root . --slug "<slug>" --run-id "<run_id>"
```

Creates `.worktrees/<slug>` off freshly-fetched `origin/<default>` with branch `iterate/<slug>`. Parse the JSON; **`{project_root}` for the rest of the run = the helper's `project_root` field**. `cd` shell into it. Exit codes: `0` ok · `2` slug collision · `3` fetch failed (STOP unless `SHIPWRIGHT_ITERATE_NO_FETCH=1`). One iterate = one worktree = one branch = one PR. `.worktrees/<slug>` is `.gitignore`'d. Re-hydrate `.env*` + `node_modules`/`.venv` per project shape. Cleanup after PR merge: `git worktree remove` + `git branch -D`.

### B2. Load Project Context (MANDATORY)

Read **all Layer 1** of `references/context-loading.md` — `CLAUDE.md`, `conventions.md`, `decision_log.md`, `architecture.md`, `shipwright_sync_config.json`, all `spec.md`, `shipwright_test_results.json`, `shipwright_events.jsonl`, `git log --oneline -20`. Missing files: warn but continue.

### C. Generate Run ID

`run_id = iterate-{YYYY-MM-DD}-{short-description}` (canonical `RUN_ID_STRICT` form). Propagate through all artifacts.

### D. Determine Intent Type

Priority: `--type` flag → `[Shipwright] Detected: ...` hook context → `classify_intent.py` → ask user (if confidence < 0.7).

### E. Assess Complexity (Two-Stage)

```bash
uv run "{plugin_root}/scripts/lib/classify_complexity.py" \
  --message "{user_message}" --sync-config "{project_root}/shipwright_sync_config.json"
```

Parse: `estimate`, `confidence`, `risk_flags`, `enforcements`, `signals`. User override: `--complexity`. Safety floor: risk flags enforce minimums. **Stage 2: Repo Scout** — Quick (trivial/small) or Thorough (medium); see `references/iteration-planning.md`. After Stage 2 complexity is **locked** (unless mid-flight escalation).

### F. Print Planned Run Summary

Print `Run ID / Intent / Complexity (+ reasoning) / Risk flags / Phases / Skipping / Safety floor`. User can adjust per Override Classes (below).

### G. Interview (complexity-gated)

| Complexity | FEATURE | CHANGE | BUG |
|------------|---------|--------|-----|
| Trivial | skip | skip | skip (reproduce instead) |
| Small | 1 confirmation Q | 1 confirmation Q | skip (reproduce instead) |
| Medium | 2-3 scoping Qs | 1-2 scoping Qs | skip (reproduce instead) |
| Large | → escape hatch | → escape hatch | → escape hatch |

**CRITICAL: Wait for user answers before proceeding to any path step.**

**Feedback Parsing Protocol** (Interview / Approval Gate / any correction): extract ALL items, echo as numbered checklist, wait for user confirmation, track as TodoWrite tasks, no silent dropping. **NEVER proceed without all feedback items captured and confirmed.**

---

## Canonical Risk Taxonomy

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

"touches_db" (ordinary query/model edits without schema changes) is NOT a risk flag. `touches_build` triggers `/shipwright-test`'s Step 3.8 (skip-rules apply: no `dev_url` → skip Lighthouse, no build artifacts → skip bundle).

---

## Override Classes

| Category | Phases | User can skip? |
|---|---|---|
| **Mandatory** | Self-review, unit test, commit, ADR, compliance, test results JSON, iterate_history, Confidence Calibration (medium+), Test Completeness Ledger (medium+) | Never skippable |
| **Safety-enforced** | Full review (when risk flags), full test suite (when shared infra), down.sql (when migrations), Boundary Probe (when `touches_io_boundary`), Confidence Calibration (small with `touches_io_boundary`), Test Completeness Ledger (small) | Only with explicit risk acknowledgment |
| **Advisory** | Design check, mini-plan, design fidelity, E2E update, external LLM review, release prompt, Confidence Calibration (trivial / small without `touches_io_boundary`), Test Completeness Ledger (trivial → auto `n/a`) | Freely skippable |
| **Complexity-gated** | Iterate spec, context scan depth | Adjustable via "make it medium/small" |

---

## Path A: FEATURE (new functionality)

Full body in `references/path-a-feature.md`. The Step 1 / Step 6 / Step 7 / Step 7.5 / Step 8 / Step 11a / Step 11b anchors stay inline here for drift-protection tests.

### Step 1: Iterate Spec (medium+ only)

Create `.shipwright/planning/iterate/{date}-{short-description}.md`. Full template in `references/path-a-feature.md`. The template MUST contain `## Confidence Calibration` with the four bullets:

```markdown
## Confidence Calibration
- **Boundaries touched:** {list from Affected Boundaries}
- **Empirical probes run:** {one-line per probe + finding}
- **Test Completeness Ledger:** {table — every testable behavior → `tested`
  (evidence) | `untestable` (closed-vocab reason_code); 0 untested-testable}
- **Confidence-pattern check:** {asymptote (depth) + coverage (breadth)}
```

### Step 6: Build (TDD — Red-Green-Refactor)

Tests first (outcomes, not internal state; one happy + one error path per AC). Implementation, verify wiring, Boundary Probe sub-step when `touches_io_boundary`. Full body in `references/path-a-feature.md`. The three governance-rule anchors stay inline so `tests/test_skill_step_6_rules_present.py` continues to fire:

- **Test-Update-Klausel** — when an iterate changes test infrastructure itself (skip semantics, hygiene rules, test conventions, this skill's checklist), it MUST update the skill's reference rules in the same diff.
- **Registry-driven SSoT meta-test rule** — when a registry in `shared/scripts/lib/*` references files/identifiers on disk, BOTH directions of drift protection MUST exist: forward (every value resolves to a file) AND reverse (every namespace-matched file has a registry entry).
- **Silent-skip CI-discipline rule** — `pytest.skip(...)` on missing-binary or cross-plugin sys.path-pollution / ImportError paths MUST hard-fail in CI with an actionable install hint. Pattern: `if os.environ.get("CI", "").lower() in ("true", "1"): pytest.fail(...)` guarding the skip.

### Step 7: Self-Review (always)

See `references/iteration-reviews.md` for the 7-point checklist (item 7: Affected Boundaries).

### Step 7.5: Confidence Calibration (mandatory at medium+, also when `touches_io_boundary`)

"Are you confident?" is unfalsifiable — replace with empirical probes per `references/confidence-anti-patterns.md`. Before F0, populate the spec's Confidence Calibration section with: (1) boundaries touched, (2) empirical probes run + finding, (3) the **Test Completeness Ledger**, (4) confidence-pattern check (asymptote depth + coverage breadth). **Override Classes:** Mandatory at medium+, Safety-enforced at small with `touches_io_boundary`, Advisory otherwise.

**Test Completeness Ledger (the empirical-completeness gate).** Principle: **testable ⇒ tested.** Enumerate every behavior this diff introduces/changes; classify each as exactly one of `tested` (cite the test + result) or `untestable` (cite a `reason_code` from the closed vocabulary in `references/confidence-anti-patterns.md` — `requires-prod-credential`, `requires-external-nondeterministic-service`, `requires-physical-device`, `requires-manual-visual-judgment`, `requires-interactive-tty`, `covered-by-existing-test`). The disposition "could-test-but-didn't" is **abolished** — "I should still test X" is a blocking work item, not a spec note. At F5, record the machine-readable block `iterate_latest.test_completeness` in `shipwright_test_results.json` (shape in `references/F5.md`); the F11 verifier `check_test_completeness_ledger` STOPs the run if any behavior is testable-but-untested, or an `untestable` row lacks a valid `reason_code`, or the enumeration is short of the AC count. **Graduated:** enforced at small/medium/large; auto `n/a` (with a one-line justification) at trivial.

### Step 8: Full Code Review (conditional)

See `references/iteration-reviews.md` for trigger rules.

### Step 11a: Author E2E Spec (always at medium+; if feature+UI at trivial/small)

See `references/design-and-testing.md` → "End-to-End Verification — Authoring".

### Step 11b: Execute E2E Spec against Dev Stack (always at medium+)

See `references/design-and-testing.md` → "End-to-End Verification — Execution". **Spec-only authoring without execution is forbidden at medium+.** Execution is verified at F0.5; the chokepoint is `shared/scripts/surface_verification.py`.

---

## Path B: CHANGE (modify existing behavior)

See `references/path-b-change.md`. Same steps as FEATURE; default Spec Impact is **MODIFY**. Step 7.5 (Confidence Calibration) applies identically — mandatory at medium+, also at small with `touches_io_boundary`.

---

## Path C: BUG (fix something broken)

BUG intent (intent-classification `kind: bug-fix`) routes through **[F-debug](references/F-debug.md)** BEFORE any fix — Iron Law: **NO FIXES WITHOUT ROOT CAUSE INVESTIGATION FIRST** (4 phases: Read Error → Reproduce → Recent Changes → Component-Boundary Instrumentation). The reviewer **rejects a fix that patches a symptom rather than the root cause** (no root-cause statement / no test pinning it). Then follow `references/path-c-bug.md` (investigation, reproduce, root-cause, write-failing-test, fix). Step 7.5 (Confidence Calibration) applies identically — mandatory at medium+, also at small with `touches_io_boundary`.

---

## 5b. Campaign Mode (Autonomous Multi-Iterate)

See `references/campaign-mode.md` for the full protocol: campaign setup, autonomous loop (init/next/record/finalize), sub-iterate-runner contract, F12 release prompt. **Review steps in autonomous-loop briefing (ADR-029):** the sub-iterate-runner contract mandates **Step 3.5 (External Plan Review)** and **Step 3.7 (Code Review Cascade)** between Build and Finalization for medium+ iterates. The runner has no `Agent` tool, so the internal code-reviewer is delegated back to the orchestrator. Skipping these review steps silently is a contract violation under ADR-029. **Manual sub-iterate stamp (campaign S1):** a hand-run sub-iterate — `/shipwright-iterate --campaign <slug> --sub-iterate-id <id> "<sub-iterate spec path>"` (or any direct invocation on a campaign sub-iterate spec) — MUST stamp its `work_completed` event exactly like the runner does: include `"campaign": "<slug>"` and `"sub_iterate_id": "<id>"` in the F5b `--event-extras-json` (see `references/F5b.md`); additive metadata, does not replace the FR-gate classification fields.

---

## 6. Phase Matrix by Complexity (NORMATIVE)

**Single Source of Truth for phase selection.** All prose, diagrams, examples MUST be consistent. Large is a "soft boundary" — force-continue supported with mandatory review + full tests.

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
| Test Completeness Ledger | n/a (auto) | always | always | always |
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

> **E2E Verification "always" at medium+ means author AND run, not author OR run.** Spec-only authorship counts as no test (see F0.5). Large routes to the escape-hatch pipeline.

---

## 7. Mid-Flight Escalation

See `references/mid-flight-escalation.md` (trivial → small → medium → large transitions, dirty-tree handling, WIP checkpoint commits). The agent can upgrade complexity mid-flight if scope is expanding.

## 8. Escape Hatch

See `references/escape-hatch.md` and `references/iteration-planning.md` (handoff file format and failure behavior). Triggered when complexity = large.

## 9. Artifact Ownership

See `references/artifact-ownership.md` (iterate spec, `spec.md`, `shipwright_events.jsonl`, ADR, `architecture.md`, mini-plan).

---

## Finalization (all paths)

**CRITICAL: F0–F11 (incl. F3a, F5a, F5b, F5c) are MANDATORY.**

> **Order matters.** F0.5 / F3 / F3a / F4 / F5 / F5a / F5b / F5c all write tracked artifacts and MUST run before F6 so a single atomic commit stages them. **F5b's `work_completed` event lands in this worktree's `shipwright_events.jsonl`, so F6 stages it and it ships in the PR** (per-tree, PR-committed model — iterate-2026-05-29-events-jsonl-worktree-commit). F0.5 is the production-time E2E gate. F6.5 (SHA patch) and F7/F7b are SKIPPED in the normal worktree flow — they exist only for legacy / out-of-band (non-worktree, replay) event recording. Do not reorder.

### F0: Fresh Verification Gate

See [F0](references/F0.md). Leak-guard (`check_iterate_isolation.py --stage f0`), then full test suite. STOP on any failure.

### F0.5: End-to-End Verification Gate

See [F0.5](references/F0.5.md). **Mandatory at medium+.** Safety-enforced at small with `touches_io_boundary` or UI. Advisory at trivial.

Four fail-closed conditions enforced by `surface_verification.py` (orchestrator) + the post-commit audit `verify_iterate_finalization.py`: (1) `surface != "none"` AND `tests_run == 0`; (2) non-zero `exit_code` after the 3-retry cap; (3) `surface == "none"` without a `justification`; (4) `surface_verification` block missing at medium+ without an opt-out. Non-zero exit at F0.5 = STOP.

**Backend-affects-Frontend rule.** If the diff touches API routes, store mutations, SSE/WS handlers, message contracts, or any code consumed by the UI — `surface = web` is mandatory even when no `client/**` file changed. The matrix `always` cell at medium+ subsumes file-path detection. Spec-only authorship counts as no test (`tests_run = 0`).

### F1 .. F12 — one-line index

| Phase | Reference | One-liner |
|---|---|---|
| F1 | [F1](references/F1.md) | `artifact_sync.py --ref "HEAD~1..HEAD"`; update specs if drift |
| F2 | [F2](references/F2.md) | Architecture update; triggers: new route/component/schema/service/write-surface/read-surface/convention |
| F3 | [F3](references/F3.md) | `write_decision_drop.py` keyed by `run_id`; ADR-NNN assigned at `/shipwright-changelog` release; field cap 1-3 sentences / 500 chars |
| F3a | [F3a](references/F3a.md) | Reflection — append learnings per `references/reflection.md` |
| F4 | [F4](references/F4.md) | `write_changelog_drop.py` → one bullet per AC under `CHANGELOG-unreleased.d/<category>/` |
| F5 | [F5](references/F5.md) | Latest-run state under `iterate_latest` in `shipwright_test_results.json` — incl. the `test_completeness` ledger block (small+) |
| F5b | [F5b](references/F5b.md) | `finalize_iterate.py` — records `work_completed` (with `commit=""`) into **this worktree's** events.jsonl BEFORE compliance regen + handoff; F6 stages it (ships in the PR) |
| F5c | [F5c](references/F5c.md) | `append_iterate_entry.py` → `.shipwright/agent_docs/iterates/<run_id>.json` atomically; 50-entry retention |
| F6 | [F6](references/F6.md) | Commit (Conventional Commits). Explicit `git add` per-path list — **incl. `shipwright_events.jsonl` when tracked**. NEVER `-A`. Footer: `Run-ID: {run_id}` + `Co-Authored-By: Claude <noreply@anthropic.com>` |
| F6.5 | [F6.5](references/F6.5.md) | **SKIP in worktree flow** — event ships with `commit=""`. Legacy/non-worktree only: `finalize_iterate.py attach-commit …` |
| F7 | [F7](references/F7.md) | Legacy/out-of-band `record_event.py`. Skip unless replaying / non-worktree. ADR-059 FR-gate applies to ALL iterates incl. BUG |
| F7b | [F7b](references/F7b.md) | `commit_event_followup.py` — seals an **out-of-band F7** main-tree append only (not the worktree flow; idempotent noop otherwise) |
| F11 | [F11](references/F11.md) | Leak-guard (`--stage f11`), push + `gh pr create` against `origin/<default>`, update handoff, run `verify_iterate_finalization.py` |
| F12 | [F12](references/F12.md) | Count pending drops; prompt for `/shipwright-changelog` once PR merges; print summary banner |

---

## Degraded Mode
See `references/degraded-mode.md` (no sync config, stale mappings, no visual-guidelines, browser-verify failure, code-reviewer unavailable, external review opt-out, pipeline handoff failure, no designs). Record degraded conditions in `shipwright_test_results.json.degraded[]`.

## Error Handling
See `references/error-handling.md` (test failures: 3-attempt circuit breaker; pre-commit hook failures: auto-fix, never `--no-verify`; missing sync config: TBD/conservative; session handoff: see `references/iteration-reviews.md`).
