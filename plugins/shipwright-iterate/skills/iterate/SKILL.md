---
name: shipwright-iterate
description: "Lightweight SDLC for ongoing changes in completed Shipwright projects.\nTRIGGER when: user asks to add a feature, fix a bug, change behavior, refactor, update, modify, or improve code in a project that has shipwright_run_config.json with status complete. Also when user describes a bug report, enhancement request, or any code-level change to a finished project.\nDO NOT TRIGGER when: user asks about project setup (/shipwright-project), planning (/shipwright-plan), initial build (/shipwright-build), deployment (/shipwright-deploy), running tests (/shipwright-test), or non-code tasks like documentation questions. Also DO NOT TRIGGER when the pipeline is still in_progress — those changes belong to the current pipeline phase."
license: MIT
compatibility: Requires uv (Python 3.11+), git repository required, completed Shipwright project
---

# Shipwright Iterate Skill

Complexity-adaptive change lifecycle for completed Shipwright projects. Detects intent (feature, change, bug), assesses complexity, runs the right amount of process.

> **How invoked:** directly via `/shipwright-iterate`, or via the `suggest_iterate.py` UserPromptSubmit hook context.
> **External review (v0.5.x+):** medium+ uses `{shared_root}/scripts/tools/external_review.py --mode iterate`, `check-external-review-keys.py`, `mark-review-state.py` (Branch A/B/C gate). Branch A makes a **second** call — `--mode architecture`, over a short brief instead of the mini-plan — asking whether the change should be built at all (`references/iteration-planning.md` → Step 3.5 step 2a). Same step, same two models, no extra row and no marker — its verdicts, findings and the reconciliation land in the iterate spec's `## Architecture Review` section and the ADR, because step 5's `plan` row takes one payload and the FIRST call already fills it.

## Phase Index — Where the prose lives

| Section | Reference |
|---|---|
| Repo Scout, Mini-Plan | [iteration-planning](references/iteration-planning.md) · [escape-hatch](references/escape-hatch.md) |
| Self-Review, Full Review, Handoff | [iteration-reviews](references/iteration-reviews.md) |
| Design Check, Testing, Visual, E2E | [design-and-testing](references/design-and-testing.md) |
| Reflection, Boundary Probes, Round-Trip, Confidence | [reflection](references/reflection.md) · [boundary-probes](references/boundary-probes.md) · [round-trip-tests](references/round-trip-tests.md) · [confidence-anti-patterns](references/confidence-anti-patterns.md) |
| Context Loading | [context-loading](references/context-loading.md) |
| Path A / B / C body (+ SIMPLIFY sub-mode) | [path-a-feature](references/path-a-feature.md) · [path-b-change](references/path-b-change.md) · [path-c-bug](references/path-c-bug.md) · [F-debug](references/F-debug.md) (BUG systematic-debugging) · [F-simplify](references/F-simplify.md) (SIMPLIFY behavior-preserving) |
| Campaign Mode, Escalation, Degraded, Errors | [campaign-mode](references/campaign-mode.md) · [mid-flight-escalation](references/mid-flight-escalation.md) · [degraded-mode](references/degraded-mode.md) · [error-handling](references/error-handling.md) |
| Repairing a red shared branch (§B1b + F11) | [main-repair](references/main-repair.md) |
| Artifact Ownership — iterate spec, `spec.md`, `shipwright_events.jsonl`, ADR, `architecture.md`, mini-plan | [artifact-ownership](references/artifact-ownership.md) |
| Phase Timing (Iterate-Rail durations, M-Pre-1) | [phase-timing](references/phase-timing.md) |
| Finalization F-phases | [F0](references/F0.md) · [F0.5](references/F0.5.md) · [F1](references/F1.md) · [F2](references/F2.md) · [F3](references/F3.md) · [F3a](references/F3a.md) · [F4](references/F4.md) · [F5](references/F5.md) · [F5b](references/F5b.md) · [F5c](references/F5c.md) · [F6](references/F6.md) · [F6.5](references/F6.5.md) · [F7](references/F7.md) · [F7b](references/F7b.md) · [F11](references/F11.md) · [F12](references/F12.md) |
| Risk Taxonomy, Override Classes, Phase Matrix | this file (inline — NORMATIVE) |

---

## CRITICAL: First Actions

**Governing rules:** read and follow `shared/constitution.md` (ALWAYS / ASK FIRST / NEVER). **BEFORE any other tools:**

### A. Print Intro Banner

```
================================================================================
SHIPWRIGHT-ITERATE: Adaptive Change Lifecycle
================================================================================
Usage: /shipwright-iterate --type feature|change|bug [--review-model opus|sonnet|haiku|inherit] [--finalization-model ...] [--plan-review-model ...] "description"
   or: Auto-detected from your prompt (via hook context)
Paths: FEATURE / CHANGE → [interview]→[spec]→[plan]→[approval]→[review]→[design]→build→test→commit
       BUG              → [spec]→reproduce→[plan]→fix→test→commit
Complexity: trivial | small | medium | large (auto-detected, overridable)
In plain words (shared index → docs/guide.md Appendix A):
  ADR: Log of architectural decisions with rationale (why this database, why this pattern)
  Conventional Commits: Standardized commit-message format (`feat:`, `fix:`, etc.) so version history is machine-readable
================================================================================
```

### B. Validate Project

Verify `shipwright_run_config.json` exists with `status: "complete"` (or `iterate_history` exists). Otherwise print the "Completed Project Required" notice and **stop**.

### B1. Resumable Iterate Run

Every iterate runs in a worktree under `.worktrees/<slug>/`. If inside a worktree (`git rev-parse --git-common-dir` resolves above cwd), resume in place. Otherwise enumerate branches with `uv run "{shared_root}/scripts/tools/list_iterate_branches.py" --project-root .` (surfaces `locked` = resumable, `stale` = housekeeping). Check `.shipwright/agent_docs/session_handoff.md` for `run_id`. Offer Resume / Abandon / Complete. **Resume/Complete replay-check:** if medium+ has no external-review marker AND `feedback_iterations > 0`, run Step 4 first. If the iterate ADR has no `Self-Review:` block, run Step 7 before commit. **Review-cascade replay-check (the canonical check — do not hand-read `session_handoff.md` for this):** run `uv run "{shared_root}/scripts/tools/record_review_pass.py" show --project-root "{project_root}" --run-id "{run_id}"` and read its `reviews` object. This is the durable, git-eventually-tracked source — `session_handoff.md`'s own auto-generated snapshot is a *secondary, best-effort* convenience refreshed only on a live session's Stop event, so a run killed mid-phase never gets it written and it cannot be trusted for this check. If `self` is still `pending`, nothing past Step 7 is due yet — resume the normal linear flow, no special action. If `self` is terminal (`completed`/`not_run`/`not_applicable`) and any of `spec`/`code`/`doubt`/`external_code` is still `pending`, the cascade started and was interrupted — resume Step 8 from there before commit.

### B1a. Worktree Isolation (unconditional)

```bash
uv run "{shared_root}/scripts/tools/setup_iterate_worktree.py" \
  --project-root . --slug "<slug>" --run-id "<run_id>"
```

Creates `.worktrees/<slug>` off freshly-fetched `origin/<default>` with branch `iterate/<slug>`. Parse the JSON; **`{project_root}` for the rest of the run = the helper's `project_root` field**. `cd` shell into it. Exit codes: `0` ok · `2` slug collision · `3` fetch failed (STOP unless `SHIPWRIGHT_ITERATE_NO_FETCH=1`). One iterate = one worktree = one branch = one PR. `.worktrees/<slug>` is `.gitignore`'d. Re-hydrate `.env*` + `node_modules`/`.venv` per project shape. Cleanup after PR merge: `git worktree remove` + `git branch -D`.

### B1b. Shared-Branch Health (one API call)

This run inherits `origin/<default>`'s state, so check it before building on it — a broken base otherwise surfaces later as a confusing F0 failure "from another session". Run `uv run "{shared_root}/scripts/tools/main_health.py" --project-root "{project_root}"`. Exit `0` green / `3` running → continue. `4` unknown → continue, but report it in the F12 summary: **unknown is never green.** `2` red → **repair `main` first, as its own small PR**, then continue with this iterate's actual task. `5` escalate → a finding-class workflow (scanner, bloat) is red: that is a finding, never an auto-repair — file the card per `escalate.keys`, then continue. Both per [main-repair](references/main-repair.md). The claim is **creating** the ref `iterate/fix-main-<sha12>` (a same-SHA `git push` succeeds for both racers and is therefore no lock); an existing claim means someone else is on it, so just proceed. The same check runs again before the arm at F11 — merging onto a red base puts the blame for the next red run on the wrong change.

### B2. Load Project Context (MANDATORY)

Load pre-Scout Layer 1 per `references/context-loading.md`; never load raw `shipwright_events.jsonl` here. After Stage-2 Repo Scout, use that reference's bounded query + canonical catalog refresh. Missing files: warn but continue.

### C. Generate Run ID

`run_id = iterate-{YYYY-MM-DD}-{short-description}` (canonical `RUN_ID_STRICT` form). Propagate through all artifacts. → **Phase Timing:** the durable `scope` mark is now stamped automatically by `setup_iterate_worktree.py` (§B1a) the moment the worktree resolves — no separate agent call needed (see [phase-timing](references/phase-timing.md)).

### D. Determine Intent Type

Priority: `--type` flag → `[Shipwright] Detected: ...` hook context → `classify_intent.py` → ask user (if confidence < 0.7). A `mode: simplify` classification (simplify/clean-up vocabulary) selects the behavior-preserving **SIMPLIFY sub-mode** (Path B → [F-simplify](references/F-simplify.md), Spec Impact NONE). → **Iterate Timing:** BUG intent → `start discovery_diagnosis --parent none`; otherwise `start planning --parent none` (see [iterate-timings](references/iterate-timings.md) for the full catalog and the producer/agent split).

### E. Assess Complexity (Two-Stage)

```bash
uv run "{plugin_root}/scripts/lib/classify_complexity.py" \
  --message "{user_message}" --sync-config "{project_root}/shipwright_sync_config.json" \
  --project-root "{project_root}" --run-id "{run_id}"
```

Parse: `estimate`, `confidence`, `risk_flags`, `enforcements`, `signals` (incl. `signals.prior_source`). Passing `--run-id` additively persists the session plan (phases/skips/risk_flags/complexity) to `.shipwright/agent_docs/iterates/{run_id}.plan.json` for the WebUI scoped Plan-Card — stdout is byte-unchanged. User override: `--complexity`. Safety floor: risk flags enforce minimums. **Fall-through default is history-calibrated, and capped at `small`:** when no scope keyword matches, the estimate is the median final complexity of the last finalized runs (`.shipwright/agent_docs/iterates/`, `prior_source: history`) instead of bare `trivial`; a keyword match always wins (`prior_source: keyword`); cold start keeps `trivial` (`prior_source: default`). **The fall-through may inform how LOW to go, never how HIGH.** `medium` is the first tier that buys an iterate spec, a mini-plan, an approval gate and an external LLM plan review, so it must be bought with *positive* evidence — a scope keyword, a risk flag, a cross-split, or the Stage-2 Repo Scout — never with the absence of evidence. The cap is also what breaks the ratchet: the prior is the median of *final* complexities and a no-keyword run's final complexity **is** the prior, so `prior = median(finals)` is self-consistent at any level and carries no information about the change; measured 2026-07-31 the store's 50 retained entries were **84% medium / 14% small / 2% trivial**, so the prior returned `medium` for every no-keyword run (trg-ee7b83e5). *That 84% is the history's composition, not the share of runs this cap flips* — the flip-rate is the no-keyword fraction, which nothing recorded until F5c began carrying `prior_source` in this same change. Under-classification stays cheap because Stage 2 confirms/upgrades and Mid-Flight Escalation exists; over-classification does not, because complexity **locks** after Stage 2. **Quick Scout must keep its diff-driven detector step** (`references/iteration-planning.md`) — Stage 1 sees no diff, so `cross_component` and the CI-supply-chain flag are message-only until then. Both F11 verifiers now recompute from the diff and enforce at **every** complexity, so a missed detection is caught mechanically at finalization rather than silently skipped (iterate-2026-08-01-coverage-gate-recompute-order) — but being caught at F11 means being blocked *after* the work is built, so the scout step is what keeps the classification honest up front. **Stage 2: Repo Scout** — Quick (trivial/small) or Thorough (medium); see `references/iteration-planning.md`. After Stage 2 complexity is **locked** (unless mid-flight escalation).

### F. Print Planned Run Summary

Resolve model tiers first (`references/iteration-planning.md` → "Model Tier Resolution"; keep the result for Step 8 and campaign-mode). Print `Run ID / Intent / Complexity (+ reasoning) / Prior source (keyword | history | default) / Risk flags / Phases / Skipping / Safety floor / Model tiers (review=<resolved> (<source>), finalization=<resolved> (<source>), plan_review=<resolved> (<source>))`. User can adjust per Override Classes (below).

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
| `touches_build` | the build/dependency graph, JS **and** Python. JS: `package.json`, `package-lock.json`, `yarn.lock`, `pnpm-lock.yaml`, `bun.lockb`, `npm-shrinkwrap.json`, `next.config.*`, `vite.config.*`, `tailwind.config.*`, `webpack.config.*`, `rollup.config.*`, `tsconfig.json`. Python: `uv.lock`, `poetry.lock`, `Pipfile`, `Pipfile.lock`, `pyproject.toml`, `setup.py`, `setup.cfg`, `requirements*.txt` | small | performance test layer (Lighthouse + bundle gate via /shipwright-test Step 3.8). **For a Python change that layer is mostly a no-op by its own skip-rules** (no `dev_url` → skip Lighthouse, no build artifacts → skip bundle); what is load-bearing there is the `small` minimum plus the flag itself, which turns on "Full Code Review — *only if risk flags*" at trivial/small. The list was JS-only until iterate-2026-07-31-it5-classification-calibration, so in a Python monorepo a dependency change raised nothing (trg-496e63a7). Scope is JS + Python by decision; Rust/Go/Ruby/PHP inputs are deliberately absent rather than forgotten |
| `touches_io_boundary` | `.env*`, `hooks.json`, `settings.json`, `*_config.json`, `*_state.json`; or anchored producer/consumer keywords (`parse_env`, `json.dump(s)?`, `json.load(s)?`, `yaml.dump`, `yaml.safe_load`) | small | round-trip test (Boundary Probe sub-step in Build TDD — see `references/boundary-probes.md` + `references/round-trip-tests.md`) |
| `cross_component` | FRAMEWORK cross-component machinery (diff-driven, `classify_complexity.CROSS_COMPONENT_FILE_PATTERNS`): merge/churn/event-log resolver (`integrate_main`, `ensure_current`, `churn_merge`, `gitattributes_*`, `resolve_churn_conflicts`, `events_log`), Claude-Code hooks + hook fan-out (`hooks.json`, `**/hooks/*.py`), pipeline phase validators (`verify_phase`, `get_phase_context`), campaign drain (`autonomous_loop`, `campaign_*`, `campaign-mode.md`) | medium | **integration coverage** — a real-scenario integration test proving the components compose (reference: `shared/tests/test_parallel_merge_cascade_integration.py`), recorded as a `category:"integration"` behavior in the Test Completeness Ledger. NON-dodgeable: the F11 verifier `check_integration_coverage` RECOMPUTES the flag from the diff, applies at **EVERY complexity**, and STOPs without it; infra failures (unobtainable diff, git fault) fail closed, and only a non-git context skips. **`medium` here is the CLASSIFICATION escalation floor — what the flag forces a *run* to be classified as — not an enforcement floor for the gate.** The two were coupled until iterate-2026-08-01-coverage-gate-recompute-order, which meant the recompute was reached only for runs that had already self-reported into the enforcing band, i.e. never for the missed-detection case it exists to catch. + full test suite |
| `touches_ci_supplychain` | the CI trust boundary (diff-driven, `risk_detectors.CI_SUPPLYCHAIN_FILE_PATTERNS`): `.github/workflows/**`, `.github/dependabot.y(a)ml`, `.github/actions/**` | small | **acknowledgement** — `.shipwright/planning/iterate/<run_id>/ci_supplychain_ack.json` must name the recorded posture decision the change is consistent with, bound to the run id AND a fingerprint of this diff's CI paths (a stale ack cannot license a later change); write it with `shared/scripts/tools/record_ci_supplychain_ack.py` and let F6's directory-level add stage it. It sits beside `reviews.json` because its old home — `iterate_latest` inside the DERIVED `shipwright_test_results.json` — made it unshippable: committing that file trips `check_no_derived_snapshots_committed` while omitting it starves this gate (both ERROR), and `restore_derived_to_head` reverted the ack outright (iterate-2026-07-28-ci-ack-per-run-home). An ack recorded the old way is still honoured under identical validation. NON-dodgeable: the F11 verifier `check_ci_supplychain_ack` RECOMPUTES the flag from the diff, applies at EVERY complexity, and fails closed when the diff is unobtainable. Mandatory review alone was REJECTED as the enforcement — webui #285 already ran a full medium iterate with external plan review and still reversed an accepted-risk posture unnoticed. It forces the change to be reasoned about and recorded; it must NEVER be read as "pin everything" (GitHub-owned actions stay on mutable tags by decision, third-party stay SHA-pinned). + mandatory review |

"touches_db" (ordinary query/model edits without schema changes) is NOT a risk flag. `touches_build` triggers `/shipwright-test`'s Step 3.8 (skip-rules apply: no `dev_url` → skip Lighthouse, no build artifacts → skip bundle).

## Override Classes

| Category | Phases | User can skip? |
|---|---|---|
| **Mandatory** | Self-review, unit test, commit, ADR, compliance, test results JSON, iterate_history, Confidence Calibration (medium+), Test Completeness Ledger (medium+), Review Record (small+ — a pass may be closed `not_run`, but never left unanswered) | Never skippable |
| **Safety-enforced** | Full review (when risk flags), full test suite (when shared infra), down.sql (when migrations), Boundary Probe (when `touches_io_boundary`), Confidence Calibration (small with `touches_io_boundary`), Test Completeness Ledger (small) | Only with explicit risk acknowledgment |
| **Advisory** | Design check, mini-plan, design fidelity, E2E update, external LLM review, release prompt, Confidence Calibration (trivial / small without `touches_io_boundary`), Test Completeness Ledger (trivial → auto `n/a`) | Freely skippable |
| **Complexity-gated** | Iterate spec, context scan depth | Adjustable via "make it medium/small" |

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

Tests first (outcomes, not internal state; one happy + one error path per AC). Implementation, verify wiring, Boundary Probe sub-step when `touches_io_boundary`. Full body in `references/path-a-feature.md`. → **Phase Timing:** emit `mark build` at entry. → **Iterate Timing:** `end planning` (or `end discovery_diagnosis`) / `start implementation --parent none` — a `mark_implementation_span.py` PostToolUse hook backstops `start implementation` from the first Write/Edit outside `.shipwright/` if this call is skipped, so the span is captured either way. The three governance-rule anchors stay inline so `tests/test_skill_step_6_rules_present.py` continues to fire:

- **Test-Update-Klausel** — when an iterate changes test infrastructure itself (skip semantics, hygiene rules, test conventions, this skill's checklist), it MUST update the skill's reference rules in the same diff.
- **Registry-driven SSoT meta-test rule** — when a registry in `shared/scripts/lib/*` references files/identifiers on disk, BOTH directions of drift protection MUST exist: forward (every value resolves to a file) AND reverse (every namespace-matched file has a registry entry).
- **Silent-skip CI-discipline rule** — `pytest.skip(...)` on missing-binary or cross-plugin sys.path-pollution / ImportError paths MUST hard-fail in CI with an actionable install hint. Pattern: `if os.environ.get("CI", "").lower() in ("true", "1"): pytest.fail(...)` guarding the skip.

### Step 7: Self-Review (always)

See `references/iteration-reviews.md` for the 7-point checklist (item 7: Affected Boundaries). → **Phase Timing:** emit `mark review` at entry. → **Iterate Timing:** `end implementation` / `start review --parent none` + `start self_review --parent review` — the same `mark_implementation_span.py` hook backstops these from the `record_review_pass.py record --review-type self --status completed` Bash call below, since self-review is unconditionally mandatory; bracket Step 8's cascade with `spec_review`/`code_review`/`doubt_review` (see [iterate-timings](references/iterate-timings.md)). **Record every review pass:** all seven types — `self` · `plan` · `plan_internal` · `code` · `doubt` · `external_code` · `spec` (Stage 1), all under `reviews` — close their own row in `.shipwright/planning/iterate/{run_id}/reviews.json` via `shared/scripts/tools/record_review_pass.py` (contract + per-pass table: `references/iteration-reviews.md` → "Recording each review pass"). The F11 verifier `check_review_record` STOPs the run while any type is still `pending` (small+; skipped at trivial), so a pass that did not run is closed EXPLICITLY with a `--disposition` naming the rule — `plan_internal` at trivial/small closes `not_applicable` naming the medium+ gate (`--disposition "internal plan review is medium+ only, this run is {complexity}"`). An empty Review row must always mean "genuinely not run", never "nobody wrote it down".

### Step 7.5: Confidence Calibration (mandatory at medium+, also when `touches_io_boundary`)

"Are you confident?" is unfalsifiable — replace with empirical probes per `references/confidence-anti-patterns.md`. Before F0, populate the spec's Confidence Calibration section with: (1) boundaries touched, (2) empirical probes run + finding, (3) the **Test Completeness Ledger**, (4) confidence-pattern check (asymptote depth + coverage breadth + **integration composition** — when `cross_component` machinery is touched, add a `category:"integration"` behavior proving the pieces compose; the F11 verifier `check_integration_coverage` recomputes the flag from the diff, applies at every complexity, and STOPs without it). **Override Classes:** Mandatory at medium+, Safety-enforced at small with `touches_io_boundary`, Advisory otherwise.

**Test Completeness Ledger (the empirical-completeness gate).** Principle: **testable ⇒ tested.** Enumerate every behavior this diff introduces/changes; classify each as exactly one of `tested` (cite the test + result) or `untestable` (cite a `reason_code` from the closed vocabulary in `references/confidence-anti-patterns.md` — `requires-prod-credential`, `requires-external-nondeterministic-service`, `requires-physical-device`, `requires-manual-visual-judgment`, `requires-interactive-tty`, `covered-by-existing-test`). The disposition "could-test-but-didn't" is **abolished** — "I should still test X" is a blocking work item, not a spec note. At F5, record the machine-readable block `iterate_latest.test_completeness` in `shipwright_test_results.json` (shape in `references/F5.md`) — and carry it in the **F5c entry** too, because that shared file is a derived snapshot the F11 integration rewinds to HEAD, and the gate now refuses a block naming another run (`references/F5c.md`); the F11 verifier `check_test_completeness_ledger` STOPs the run if any behavior is testable-but-untested, or an `untestable` row lacks a valid `reason_code`, or the enumeration is short of the AC count. **Graduated:** enforced at small/medium/large; auto `n/a` (with a one-line justification) at trivial.

### Step 8: Full Code Review (conditional)

See `references/iteration-reviews.md` for trigger rules. **A standing grant in `CLAUDE.md` outranks this — if the project states that review subagents are requested by default, spawn them and do NOT ask.** Only when no such grant exists and a session policy gates spawning: ask for the go-ahead as your FIRST action here — before Stage 1. Such a policy (e.g. a standing *"do not call the Agent tool unless the user requested it"*) is **conditional**: one sentence from the operator lifts it for the rest of the session. It is not a capability limit. Ask only when all three hold — the cascade is required for this diff; the `Agent` tool is in **this agent's capabilities** (asking without it wins a "yes" and fails anyway); and permission was not **already given earlier in this session** (it holds for the whole session — do not re-ask). A question asked at finalization buys nothing, because the work is already built. **If the answer is no**, that is blocker #4 — follow the escalation ladder in `references/iteration-reviews.md` (external review mandatory; `code` and `doubt` recorded `not_run` with a disposition naming *operator-declined*). **Under `--autonomous`** you cannot block to ask — but that prevents *acquiring* permission, **not using permission already held**; only when it is absent and unobtainable do you record `code = not_run` naming the mode, run the external review, and surface the ungated pass in the **closing run summary (F12)** so the operator can lift it next time. **This session spawns the cascade itself** — a standalone iterate has the `Agent` tool, so there is no delegate and nothing to wait for: `spec-reviewer` (Stage 1, **HARD-GATE** — a REJECT blocks Stage 2 until the diff is fixed and re-reviewed) → `code-reviewer` (Stage 2) → `doubt-reviewer` (Stage 3, conditional, advisory-must-address). **Pass `model=<the review tier resolved in §F>` to the Agent tool at each of the three spawns** (omit the parameter when the resolved value is `inherit` — the Agent tool has no `inherit` literal of its own). **State the run_id in plain text in every spawn prompt** (e.g. "This review is part of iterate run `{run_id}`.") — the `SubagentStop` salvage hook (`write-review-payload-on-stop.py`) can only find it in the subagent's own transcript, never from an env var. **The instant each subagent returns, write its reply to its payload file and call `record_review_pass.py record` before any other reasoning or spawning the next reviewer** — this is a mitigation, not a guarantee (it is agent-followed prose, not code-enforced; the salvage hook above is the code-level backstop for exactly the window this instruction cannot close by itself). It runs **before F6 (commit)**, because a review that lands after the commit reviews something already shipped. It reviews the **code diff**; artifacts written afterwards by Steps 11a/11b and finalization ship in the same commit unreviewed, so "before F6" buys *not after*, not *reviews everything that ships*. **Every stage closes its own row**: `spec` from Stage 1, `code` from Stage 2 (`--from code-reviewer`), `doubt` from Stage 3 — every `record_review_pass.py record` call for these three carries `--model-tier "{resolved_review_tier}"` (the same value passed at the spawn above). Stage 1's row is an ordinary `reviews` key. It was parked in a sibling `gates` object while the webui refused to read a record carrying a sixth key; that reader now renders review types it does not recognise, so `spec` was promoted (`references/iteration-reviews.md`). Records written before the promotion keep `spec` under `gates` and are still read from there — permanently, since they are immutable. The gate enforces the cascade's own ordering: a `code` row recorded `completed` while `spec` is not `completed` FAILS, because Stage 2 cannot legitimately have run without its HARD-GATE passing first. A completed `code`/`external_code` row must also carry evidence a review happened — findings, a provider, a raw excerpt, or a `recorded_by` naming an adapter other than `none`. The runner contract's "delegated" wording (§5b) is **campaign-only** and does not apply here.

### Step 11a: Author E2E Spec (always at medium+; if feature+UI at trivial/small)

See `references/design-and-testing.md` → "End-to-End Verification — Authoring".

### Step 11b: Execute E2E Spec against Dev Stack (always at medium+)

See `references/design-and-testing.md` → "End-to-End Verification — Execution". **Spec-only authoring without execution is forbidden at medium+.** Execution is verified at F0.5; the chokepoint is `shared/scripts/surface_verification.py`.

---

## Path B: CHANGE (modify existing behavior)

See `references/path-b-change.md`. Same steps as FEATURE; default Spec Impact is **MODIFY**. Step 7.5 (Confidence Calibration) applies identically — mandatory at medium+, also at small with `touches_io_boundary`. **SIMPLIFY sub-mode** — when intent-classification returns `mode: simplify` (*simplify / clean up / declutter / streamline / tidy*) OR Spec Impact is **NONE** (behavior-preserving refactor): route through **[F-simplify](references/F-simplify.md)** — Behavior-Snapshot (`{shared_root}/scripts/tools/behavior_snapshot.py snapshot`, refuses a red baseline) → Simplify (Five Principles + Chesterton-Fence + the shared reducibility catalog D·A·X·C·S·M·P·T) → Behavior-Verify (`behavior_snapshot.py verify`). The reviewer **rejects** a simplify that ships behavior drift or removed test coverage (*fewer lines is not the goal*); Spec Impact is forced **NONE**. The gate is only as strong as coverage, so removed coverage is a hard reject.

---

## Path C: BUG (fix something broken)

BUG intent (intent-classification `kind: bug-fix`) routes through **[F-debug](references/F-debug.md)** BEFORE any fix — Iron Law: **NO FIXES WITHOUT ROOT CAUSE INVESTIGATION FIRST** (4 phases: Read Error → Reproduce → Recent Changes → Component-Boundary Instrumentation). The reviewer **rejects a fix that patches a symptom rather than the root cause** (no root-cause statement / no test pinning it). Then follow `references/path-c-bug.md` (investigation, reproduce, root-cause, write-failing-test, fix). Step 7.5 (Confidence Calibration) applies identically — mandatory at medium+, also at small with `touches_io_boundary`.

---

## 5b. Campaign Mode (Autonomous Multi-Iterate)

See `references/campaign-mode.md` for the full protocol: campaign setup, autonomous **interleaved-serial** loop (init/next/record/**merge**/finalize — build one sub-iterate → PR → CI-green → merge → next from fresh `origin/main`; `branch_strategy: serial` is the default), sub-iterate-runner contract, F12 release prompt. **Review steps in autonomous-loop briefing (ADR-029 — campaign mode ONLY):** the sub-iterate-runner contract mandates **Step 3.4 (Diff-Driven Risk Re-Check)**, **Step 3.5 (External Plan Review)** and **Step 3.7 (Code Review Cascade)** between Build and Finalization for medium+ iterates. **Step 3.4 runs ALWAYS and comes first**, because the other two gate on flags a campaign unit cannot otherwise have: the runner classifies once from the sub-iterate spec *text* and never reaches the Stage-2 Repo Scout, so every diff-driven detector is structurally silent until 3.4 re-decides from the real change set. It also raises the complexity F5c records — `check_integration_coverage` reads it there and green-SKIPs below `medium` — and STOPs the unit when the diff touches the CI trust boundary, since that acknowledgement is an operator's to write. In campaign mode the runner has no `Agent` tool, so the internal code-reviewer is delegated back to the orchestrator; that limit is a fact about the *runner subagent*, **not** about iterates in general — a standalone iterate spawns the cascade itself (Step 8). Skipping these review steps silently is a contract violation under ADR-029. **Manual sub-iterate stamp (campaign S1):** a hand-run sub-iterate — `/shipwright-iterate --campaign <slug> --sub-iterate-id <id> "<sub-iterate spec path>"` (or any direct invocation on a campaign sub-iterate spec) — MUST stamp its `work_completed` event exactly like the runner does: include `"campaign": "<slug>"` and `"sub_iterate_id": "<id>"` in the F5b `--event-extras-json` (see `references/F5b.md`); additive metadata, does not replace the FR-gate classification fields.

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
| External LLM Review | skip | skip | auto (+ a 2nd `--mode architecture` call over a brief, same step) | — |
| Design Check | skip | Tier 1 (text) | Tier 2 (markdown) | — |
| Build (TDD) | always | always | always | — |
| Boundary Probe | skip | if `touches_io_boundary` | if `touches_io_boundary` | — |
| Self-Review | always | always | always | — |
| Confidence Calibration | skip | if `touches_io_boundary` | always | always |
| Test Completeness Ledger | n/a (auto) | always | always | always |
| Integration Coverage (cross-component) | if `cross_component` | if `cross_component` | if `cross_component` | if `cross_component` |
| Full Code Review | only if risk flags | only if risk flags | always | — |
| Review Record (all 6 types closed) | n/a (auto) | always | always | always |
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

> **Integration Coverage vs the Ledger at trivial — the two rows above do not contradict each other.** The Ledger is auto-`n/a` at trivial, but Integration Coverage still fires there when the diff touches `cross_component` machinery. Both hold because `check_integration_coverage` reads only `test_completeness.behaviors` — never `status`, and (since iterate-2026-08-01-coverage-gate-recompute-order) never the recorded complexity. So a trivial run that touches that machinery records the one `category:"integration"` behavior in its F5c entry and passes; it does **not** have to escalate to `medium` first, and it does not owe the rest of the Ledger. Escalating is the right move only when the change genuinely warrants the fuller process.

---

## 7. Mid-Flight Escalation

See `references/mid-flight-escalation.md` (trivial → small → medium → large transitions, dirty-tree handling, WIP checkpoint commits). The agent can upgrade complexity mid-flight if scope is expanding.

## 8. Escape Hatch

See `references/escape-hatch.md` and `references/iteration-planning.md` (handoff file format and failure behavior). Triggered when complexity = large.

## Finalization (all paths)

**CRITICAL: F0–F11 (incl. F3a, F5a, F5b, F5c) are MANDATORY.** (→ Phase Timing: `mark test` at F0, `mark finalize` at F1 — see [phase-timing](references/phase-timing.md). → Iterate Timing: at F0, `end review` / `start verification --parent none` — `pre_f0_validation`/`f0_queue`/`canonical_f0_active` self-instrument, do not mark them by hand; at F1, `end verification` / `start finalization --parent none`; at F11, `end finalization` — `deliver_pr.py` self-records its own `delivery`/`delivery_wait`/`ci_wait` spans, no agent mark needed. On a `checks_failed` verdict, bracket the diagnose→fix→re-push work with `start`/`end post_ci_remediation --parent delivery`. See [iterate-timings](references/iterate-timings.md).)

> **Order matters.** F0.5 / F3 / F3a / F4 / F5 / F5a / F5b / F5c all write tracked artifacts and MUST run before F6 so a single atomic commit stages them. **F5b's `work_completed` event lands in this worktree's `shipwright_events.jsonl`, so F6 stages it and it ships in the PR** (per-tree, PR-committed model — iterate-2026-05-29-events-jsonl-worktree-commit). F0.5 is the production-time E2E gate. F6.5 (SHA patch) and F7/F7b are SKIPPED in the normal worktree flow — they exist only for legacy / out-of-band (non-worktree, replay) event recording. Do not reorder. **Speed (optional):** F1/F3/F4/F5c/F5b MAY be driven in ONE call via `finalize_bundle.py` (pure orchestrator; F5 before it, F2/F3a/F6 stay manual; whole-bundle re-run is safe) — see [F-finalize-bundle](references/F-finalize-bundle.md).

### F0: Fresh Verification Gate

See [F0](references/F0.md). Leak-guard (`check_iterate_isolation.py --stage f0`), then the mirrored merge gates where the project has them (`scripts/verify_local.py`, guarded on the file existing), then full test suite. STOP on any failure.

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
| F5c | [F5c](references/F5c.md) | Validate current-run test results, install exact bytes as immutable `<run_id>.test-results.json`, then write the existing `<run_id>.json` summary; summary retention stays 50 |
| F6 | [F6](references/F6.md) | Commit (Conventional Commits). Explicit `git add` per-path list — **incl. `shipwright_events.jsonl` when tracked**. NEVER `-A`. Footer: `Run-ID: {run_id}` + `Co-Authored-By: Claude <noreply@anthropic.com>` |
| F6.5 | [F6.5](references/F6.5.md) | **SKIP in worktree flow** — event ships with `commit=""`. Legacy/non-worktree only: `finalize_iterate.py attach-commit …` |
| F7 | [F7](references/F7.md) | Legacy/out-of-band `record_event.py`. Skip unless replaying / non-worktree. ADR-059 FR-gate applies to ALL iterates incl. BUG |
| F7b | [F7b](references/F7b.md) | `commit_event_followup.py` — seals an **out-of-band F7** main-tree append only (not the worktree flow; idempotent noop otherwise) |
| F11 | [F11](references/F11.md) | Leak-guard (`--stage f11`), `ensure_current.py` refresh-if-behind, then re-run the guarded `verify_local.py` mirror before **every** F11 push of the regenerated tree (**late STOP after F6 is accepted**), push + `gh pr create` against `origin/<default>`, update handoff, run `verify_iterate_finalization.py`, then **`deliver_pr.py`** — the delivery ladder: check the PR is this run's, arm fail-soft `gh pr merge --auto --squash` (iterate/* only; deferred under campaign `SHIPWRIGHT_ITERATE_AUTOMERGE=0` — orchestrator merges each PR in turn, interleaved-serial), and where the host structurally *cannot* arm, wait for green → refresh → re-verify → merge pinned to the verified commit. Delivered = MERGED + green (no shoot-and-forget); the summary names WHO merged it and how many checks the host ran |
| F12 | [F12](references/F12.md) | Count pending drops; prompt for `/shipwright-changelog` once PR merges; print summary banner |

## Degraded Mode & Error Handling
See `references/degraded-mode.md` (no sync config, stale mappings, no visual-guidelines, browser-verify failure, code-reviewer unavailable, external review opt-out, pipeline handoff failure, no designs) — record degraded conditions in `shipwright_test_results.json.degraded[]`. See `references/error-handling.md` (test failures: 3-attempt circuit breaker; pre-commit hook failures: auto-fix, never `--no-verify`; missing sync config: TBD/conservative; session handoff: see `references/iteration-reviews.md`).
