# Architecture — shipwright
<!-- shipwright:architecture v=2 last-sync=932e0d221ea1 -->

## System Overview

```mermaid
flowchart TB
  CC["Claude Code host<br/>loads plugins from ~/.claude/plugins/cache/shipwright/ (runtime cache)"]

  subgraph "Monorepo (this repo)"
    plugins["plugins/ — 14 phase plugins<br/>run · project · design · plan · build · test<br/>security · deploy · changelog · compliance<br/>iterate · preview · adopt · grade"]
    shared["shared/ — cross-plugin code<br/>contracts (ADR-088) · profiles · templates<br/>prompts · schemas · config · scripts"]
  end

  subgraph "Target project (per repo)"
    artifacts["CLAUDE.md · shipwright_*_config.json<br/>shipwright_events.jsonl (append-only)<br/>.shipwright/ — agent_docs · planning<br/>compliance · designs · triage.jsonl"]
  end

  gh["GitHub<br/>CI gates (ci · security · pr-review · codeql)<br/>PR auto-merge · findings API"]

  CC -->|runs| plugins
  plugins -->|import| shared
  plugins -->|read / write| artifacts
  plugins -->|push · PR| gh
  gh -->|findings to triage| artifacts
```

## Stack

| Layer | Technology | Notes |
|-------|-----------|-------|
| Frontend | — | — |
| Backend | — | — |
| Database | — | — |
| Auth | — | — |
| Runtime | python | — |

## Layers Detected

- **docs**: `docs`
- **infrastructure**: `scripts`
- **tests**: `Spec`, `integration-tests`


## Key Architecture Decisions

See `decision_log.md` for detailed ADRs. Profile-level decisions (stack, auth pattern, DB strategy, folder structure) are defined by the stack profile (`python-plugin-monorepo`).

## Data Flow

Shipwright is a monorepo of Claude Code plugins — one per SDLC phase — that
operate on a **target project** (this monorepo grades itself, so it is also its
own target). Work is never ad-hoc: each phase is a skill, and the phases
coordinate through four shared channels described below. This section documents
the steady-state data flow; per-change history lives in `## Architecture Updates`
and `decision_log.md`, not here.

### Plugins

**Layout.** Every phase is a plugin under `plugins/<phase>/` with the standard
Claude Code layout: `.claude-plugin/plugin.json`, `hooks/hooks.json`,
`skills/<phase>/SKILL.md`, `agents/` (subagent definitions), `scripts/`
(`checks`, `hooks`, `lib`, `tools`), `tests/`, and `pyproject.toml`. Cross-plugin
code lives under `shared/` (`scripts`, `contracts`, `profiles`, `templates`,
`prompts`, `config`, `schemas`).

**Cross-plugin imports.** `shared/contracts/` (ADR-088) is the *only* supported
entry point for one plugin to import another — the re-export facades
(`shared.contracts.compliance`, `shared.contracts.iterate`) shield consumers from
refactors of the underlying internals. Direct deep imports across plugins are a
convention violation.

**How phases communicate.** Four channels, all rooted in the target project:

- **iterate-2026-07-19-one-discovery-function** (2026-07-19): Component - new shared leaf `lib/planning_discovery.py` is the SINGLE walk over `.shipwright/planning/`; all 15 discovery call sites across 6 import realms delegate to it, each passing the flags (`guard`/`sort`/`include_iterate`/`recursive`/`require`) reproducing its own behaviour, so the divergence is explicit in one place instead of invisible in fifteen. Byte-identical per the S1 golden corpus. `lib/adr_headers.py` split out of `drift_parsers` to hold its ceiling. -> decision_log (Run-ID).
- **`SHIPWRIGHT_SESSION_ID`** — one unified session id across every plugin in a
  run, so hooks and artifacts written by different phases correlate.
- **`shipwright_*_config.json`** — the per-phase config files written into the
  target project root (`shipwright_run_config.json` is authoritative for pipeline
  mode and step state; writes are atomic + path-lock-coordinated via
  `run_config_store.py`).
- **`shipwright_events.jsonl`** — an append-only, **per-tree, PR-committed**
  event log (`phase_started`/`phase_completed`/`phase_failed`, `work_completed`,
  `test_run`, `grade_snapshot`, …). It is the durable spine every producer reads
  from and every derived view (RTM, dashboard, campaign status, WebUI rails)
  reduces over. `resolve_events_path` returns `<project_root>/shipwright_events.jsonl`
  literally; the iterate's own event is recorded in its worktree and ships in the PR.
- **`hooks.json`** — the single source of truth for between-phase actions and
  quality gates. What fires when is documented in `docs/hooks-and-pipeline.md`.

**Pipeline mode.** `single_session` is the sole pipeline mode: one conversation
drives every phase as a subagent (the external per-phase-session engine was
removed). The orchestrator loop resolves each phase, claims it, runs the
phase-runner, and applies the result; `gate_catalog.json` + `lib/gate_policy.py`
decide which gates auto-answer vs. require approval vs. hard-stop.

**Decision & memory trail.** Architecture/convention memory is curated in
`.shipwright/agent_docs/` (`architecture.md`, `conventions.md`, canonical H3 ADRs
in `decision_log.md`). Iterates write run-id-keyed drops to
`.shipwright/agent_docs/decision-drops/`; `aggregate_decisions.py` folds them into
`decision_log.md` with sequential `ADR-NNN` at release. Per-iterate/per-phase
artifacts live under `.shipwright/planning/` and `.shipwright/compliance/`.

**Worktree isolation.** Every `/shipwright-iterate` run executes in its own git
worktree under `.worktrees/<slug>/` on branch `iterate/<slug>`, cut from
freshly-fetched `origin/<default>`. A leak-guard (`check_iterate_isolation.py`)
diffs the main tree against a per-run snapshot and fails closed on any write that
escapes the worktree.

**Runtime plugin cache.** Claude Code loads plugins at runtime from
`~/.claude/plugins/cache/shipwright/`, **not** from this repo. Plugin-side edits
(`plugins/*`, `shared/*`, any `SKILL.md`) reach runtime only after
`scripts/update-marketplace.sh`; `scripts/check_plugin_cache_sync.py` detects
drift. (End users consuming the published plugins do not need this step.)

**Secrets.** Secrets live exclusively in `<project_root>/.env.local`, scaffolded
by `/shipwright-adopt` (ADR-021) and read by
`shared/scripts/lib/env.py::load_shipwright_env` — the framework external-review
keys (`OPENROUTER_API_KEY`, `GEMINI_API_KEY`, `OPENAI_API_KEY`) plus the active
profile's `required_env_vars`. The file is git-ignored before write; a
`.gitignore` enforcement failure aborts the scaffold.

### GitHub

GitHub is both a **gate** (CI must be green to merge) and a **findings source**
(alerts and failed runs flow back into the local backlog). Both directions are
wired into the pipeline.

**CI gates (`.github/workflows/`).** The Required Checks that gate merge to
`main`:

- `ci.yml` — the hard lint gate (`uvx ruff@0.15.15 check .`, no `|| true`) + the
  Python test suites + the **diff-coverage gate** (`.github/actions/diff-coverage-gate`;
  <80% of changed lines vs `origin/main` fails closed).
- `security.yml` — the scanner chain (Semgrep/Trivy/gitleaks) → `findings.json`
  + SARIF; the critical-gate fails **closed** on a degraded or critical scan.
- `pr-review.yml` — the Tier-3 external-LLM PR review; it is the 6th Required
  Check in the auto-merge (B4.5) design and runs only for external-contributor,
  sensitive-path (`plugins/*/{hooks,skills,agents}/`, `.github/workflows/`), or
  `needs-review`-labelled PRs (Tier 1/2 stay green via a skipped `needs:` job).
- `codeql.yml` (code scanning), `bloat-check.yml` (anti-ratchet file-size
  regression), `grade-empirical.yml` (Control-Grade projector suite).

**Findings → Triage Inbox.** A single throttled `SessionStart` hook
(`import_github_findings.py`, registered once in shipwright-iterate) pulls three
GitHub sources via the `gh` CLI and emits them as `source="github"` triage
action-units (dedup-keyed, auto-resolve scoped so a failed fetch never
mass-resolves):

- code-scanning / Dependabot / secret-scanning alerts + the latest failed
  default-branch CI run per workflow (`github_api.py`, `github_triage/`).
- `gh-security:{owner}/{repo}` — when GHAS Code Scanning is unavailable (typical
  on private repos), it falls back to the `security.yml` `security-scan-results`
  artifact (freshness-gated), parsing `findings.json`/SARIF directly.
- `gh-pr-ci:{pr}` — failed hard-gates on an **open** PR, so an armed auto-merge
  can't sit waiting on a red PR unnoticed (`github_pr_api.py`).

**Findings sink.** All producers append to `<project_root>/.shipwright/triage.jsonl`
(git-tracked, per-tree, append-only) via
`triage.py::append_triage_item_idempotent`. A gitignored per-tree **outbox** +
sweep-to-PR-branch mechanism ensures appends made off the main tree still reach
origin. Consumers regenerate `triage_inbox.md` and the Command Center WebUI
Triage tab; `refresh_ci_security.py` folds the latest `security.yml` findings into
a tracked `.shipwright/compliance/ci-security.json` that lights the compliance
dashboard's CI-Security section and the Control-Grade Security dimension.

**Auto-merge.** With all Required Checks green (and GHAS review threads
resolved), iterate F11 brings the branch current through `integrate_main` and
arms `gh pr merge --auto --squash`; "delivered" means merged + green, verified by
`watch_pr_delivery.py` (no shoot-and-forget).

## See also

_Existing user-facing documentation discovered by /shipwright-adopt._

- [`README.md`](../../README.md)
- [`docs/guide.md`](../../docs/guide.md)

## Architecture Updates
> **One line per change** — always-loaded Layer-1 context, so every line costs tokens on every future iterate. Format: `- **<run_id|ADR-NNN>** (YYYY-MM-DD): <Impact> — <one sentence: what + key surface>. → decision_log (Run-ID/ADR)`. **Budget ≤ 600 chars; detail goes in the ADR / `.shipwright/planning/adr/`, not here.** Enforced repo-agnostically (incl. adopted repos) by the F11 verifier + `shared/scripts/tools/check_agent_doc_budget.py` (SSoT `lib.agent_doc_budget`); see `references/F2.md`. Bullet **shape** (a `run_id`|`ADR-NNN` anchor, an `<Impact> —` lead, and a `→` pointer — no `Campaign`/`sub_iterate`/free-text) is enforced from 2026-06-28 by `check_agent_doc_shape` (SSoT `lib.agent_doc_shape`); the release aggregator writes no duplicate `ADR-NNN` bullet — the run_id line is the single canonical entry. Full verbatim prose for compacted entries lives in [`../planning/adr/_archive-agent-doc-updates.md`](../planning/adr/_archive-agent-doc-updates.md). Routing (`lib.architecture_doc.IMPACT_TARGETS`): `convention`-impact → [`conventions.md`](conventions.md) `## Convention Updates`; only `component` / `data-flow` live here.
- **iterate-2026-07-23-tests-skipped-tracking** (2026-07-23): Component — new shared SSOT `shared/scripts/tests_block.py` (`validate_tests_block`/`skip_suffix`/`progression_result`, top-level per ADR-045) gives the record_event write-guard, the D4 detective, the test-evidence renderer and the build dashboard one `isinstance(int)` skip predicate + `total-passed-skipped` failure arithmetic; work_completed events gain a first-class `tests.skipped` and D4 is re-enabled (bloat exception ADR-111). → decision_log (Run-ID).
- **iterate-2026-07-20-converge-table-shape** (2026-07-20): Data-flow — both FR-table producers emit ONE shape `| ID | Area | Name | Priority | Description | Basis | Layers |` from `lib/fr_table_shape.py`, which also owns the `(inferred)` marker the compliance parser imports (one grammar, both directions); `Basis` (closed vocabulary `lib/fr_basis.py`, enforced by new Group I5) replaces the `Source` path, `Area` renders from the id's group digit and is never stored, and machine-emitted `Layers` cells are marked so provenance stays advisory. → decision_log (Run-ID).
- **iterate-2026-07-20-namespace-from-requirement-id** (2026-07-20): Data-flow — the traceability manifest (schema 2→3) keys requirements by a namespace DERIVED from the FR id (`01::FR-01.03`) instead of the spec's directory (`01-adopted::FR-01.03`), so a split rename no longer rewrites every key; `Requirement.namespace` is a read-only property, and two ACTIVE rows claiming one key fail regeneration closed (a tombstone is exempt and never displaces the live node). → decision_log (Run-ID).
- **iterate-2026-07-18-fr-fold-map-resolution** (2026-07-18): Component — new shared contract `lib/fr_fold_map.py` (+ `_fr_fold_map_parse`) parses a spec's `## FR-Fold-Map` alias table and resolves a tagged FR id to its surviving capability FR; consumed by BOTH the compliance `test_links` collector (via `_test_links_fold`) and the shared backfill engine, so a granular `@covers` tag survives a taxonomy fold instead of orphaning. Resolution is fallback-only; retirement beats folding; broken edges fail closed into the manifest's new optional `fold_map`/`fold_defects`. → decision_log (Run-ID).
- **iterate-2026-07-17-arch-doc-refresh-harden** (2026-07-17): Component — new `lib/agent_doc_shape.py` SSoT + repo-agnostic CLI/F11 verifier `check_agent_doc_shape` enforce the canonical changelog-bullet grammar (`run_id|ADR-NNN` anchor + `<Impact> —` + `→ decision_log`) on the two `…Updates` sections; the release aggregator stops appending a dup `ADR-NNN` bullet when the F2 run_id bullet exists (section-scoped `run_id_documented_for_impact`); `_append_architecture_update` canonicalized; System-Overview mermaid + Data-Flow (Plugins/GitHub) refreshed. → decision_log (Run-ID)
- **iterate-2026-07-15-shared-backfill-engine** (2026-07-16): Component — new shared retrofit engine `tools/backfill_test_links.py` (+ `_lib` legs `backfill_scan/signals/write/llm`) that maps a repo's existing tests to FRs deterministic-first (path-token/unique-split/introducing-commit), LLM-assisted-second (opt-in, advisory-only, R4-bounded payload). Auto-writes only a deterministic single-FR match; lists proposals; surfaces `confirmed`/`possible`/`unmapped` orphans, never auto-deleting. Its `@FR` tags feed the TT1 manifest; shared by adopt (TT7) + retrofit (TT8). → decision_log (Run-ID).
- **iterate-2026-07-15-removal-crosslayer-gates** (2026-07-16): Component — two ENFORCING F11 traceability gates in shared `tools/verifiers` (`run_all_checks`): `removal_coverage` (a removed FR's base-linked tests must be deleted/retargeted, else HARD) and `cross_layer_coverage` (a behaviour-changed FR needs an executed-passing test at each required_layer). Both REGENERATE base+head manifests + the evidence index from staged reports (R3, never the committed artifact); + shared emit-side `lib/evidence_drop.py`. → decision_log (Run-ID).
- **iterate-2026-07-15-layer-aware-rtm-and-gates** (2026-07-16): Component — the RTM renders per-FR `Unit | Integration | E2E` coverage from the TT1 manifest; Group-D gains `D-orphan` (a test tagged with a removed/absent FR) + `D-layer` (an active FR missing an executed-passing test at a required layer; explicit FAIL / legacy advisory, fan-out fail-closed) in new `_group_d_traceability.py`; D1 hardened (a tested event AND, for explicit FRs, a real manifest link). New `_rtm_layer_columns.py` sibling keeps the capped rtm_generator/group_d net-neutral. → decision_log (Run-ID).
- **iterate-2026-07-15-contracts-and-harness** (2026-07-15): Component — froze the requirement→test traceability contracts (P1 prereq, DORMANT until a collector/gate wires them): new compliance `lib/traceability_schema.json` (manifest v2 Draft 2020-12, structurally enforcing skipped≠covered + removed⟹orphan + required-layer coverage) + shared `lib/requirement_model.py` + `lib/fr_tag_grammar.py` (@FR tag reference parser) + a panel-verified answer-key fixture package under compliance `tests/fixtures/traceability/`. → decision_log (Run-ID).
- **iterate-2026-07-14-remove-multi-session** (2026-07-14): Component — `single_session` is the SOLE pipeline mode; the external per-phase-session engine is DELETED (the `phase_session_start`/`_stop`/`phase_user_prompt_validate` trio + 3 helpers, deregistered from all 8 phase plugins, emptying their `UserPromptSubmit`). The master drives each phase as a subagent, so the pipeline runs on every surface. Invariant: drivable IFF the explicit `mode` literal, enforced at every advancing entry point but never in the read path; `gate_policy.INERT_MODE` is the new sentinel. → decision_log (Run-ID).
- **iterate-2026-07-14-webui-render-contract** (2026-07-14): Component — grade's `ReportModel` (`--format json`) + adopt's `snapshot.json` are VERSIONED cross-repo contracts for the Command Center WebUI: both carry `schema_version` (major=breaking → consumer refuses to render; minor=additive). New shared `lib/contract_skeleton.py` (JSON wire-shape diff; nullable container = breaking) + `lib/contract_baseline.py` (baseline = `origin/main`, unrewritable by a PR) back a per-producer bump gate. New frozen read-surface: `<plugin>/tests/contracts/<stem>-<ver>.json`. → decision_log (Run-ID).
- **iterate-2026-07-11-iterate-phase-timing** (2026-07-11): Data-flow — iterate finalize folds per-phase durations into its `work_completed` event as `phase_timings[{phase,started,duration_ms}]` (M-Pre-1 iterate half, pipeline-PhaseRail counterpart); the SKILL marks the 5 Iterate-Rail groups (`scope build review test finalize`) via new `iterate_phase_timing.py` into a gitignored `<run_id>.phase_timings.jsonl` sidecar (new write/read surface), aggregated by new `lib/iterate_phase_groups.py`. Additive; no sidecar → event unchanged. → decision_log (Run-ID).
- **iterate-2026-07-11-phase-completed-per-split** (2026-07-11): Data-flow — phase events in `shipwright_events.jsonl` gain a top-level `splitId`; `phase_completed` dedups on `(phase, splitId)` not phase-only, so a multi-split phase (build/plan) records one end per split (per-phase span = min `phase_started`..max `phase_completed`; per-split bars). `record_event` `--split-id` + 3 emitters forward it; 4 phase-count/latest-`ts` consumers de-duped by phase; WebUI PhaseRail follow-up (trg-941d870b). → decision_log (Run-ID).
- **iterate-2026-07-10-adopt-brief-plainbank** (2026-07-11): Data-flow — /shipwright-adopt now accepts a WebUI wizard brief (`--brief`); `brief_intake.py` is promoted to `shared/scripts/lib/` (one helper for run + adopt) and a new `adopt_brief_intake.py` maps the brief onto Step C (description → product_description pre-filled; profile + scope stay scan-gated), reusing it via the ADR-045-safe `spec_from_file_location` loader. → decision_log (Run-ID).
- **iterate-2026-07-10-emit-phase-started** (2026-07-11): Data-flow — the durable event log now pairs a `phase_started` at each PIPELINE phase entry with the existing `phase_completed`/`phase_failed` end, in both run modes (multi_session SessionStart/Stop hooks; single_session `single-session-next`/`-apply` via `orchestrator_pkg.events` + shared `lib/phase_event_emit.py`), so the WebUI PhaseRail derives per-phase durations from the tracked log alone (M-Pre-1). Best-effort/additive; `phase_task_lifecycle` stays pure (ADR-045). → decision_log (Run-ID).
- **iterate-2026-07-08-ss6-external-review-fix** (2026-07-08): Data-flow — the external LLM review gate (`external_review.py`) now fails loud when keys are present but 0 reviews succeed: new `scripts/lib/external_review_degraded.py::finalize_review_output` sets `success:false` + `degraded:true` + non-zero exit + stderr banner (was a hardcoded `success:true` that let callers silently self-review); also fixes the direct-OpenAI `max_tokens`→`max_completion_tokens` param (gpt-5.x) in external_review.py + `lib/llm_review.py`. → decision_log (Run-ID).
- **iterate-2026-07-08-ss5-resumability** (2026-07-08): Component — single-session pipeline SS5: resumability/recovery + observability. New `single_session/observability.py` (append-only `.shipwright/run_loop_events.jsonl`, 7 event types, best-effort) + `orchestrator_pkg/single_session_recovery.py` (`resume_run` read-only card/`--confirm`, `mark_human_gate`, `recover_single_session`) + CLI `single-session-resume`/`-gate`/`-recover`, all mode+runId gated. `multi_session` untouched (back-compat suite). → decision_log (Run-ID).
- **iterate-2026-07-07-ss3-orchestrator-loop** (2026-07-07): Component — single-session pipeline SS3: the orchestrator LOOP (`single_session_loop.py` + `single_session_cli.py`; CLI `single-session-next`/`single-session-apply`) drives every phase under `mode==single_session` from ONE conversation — resolve → claim → phase-runner subagent → apply. Reuses `phase_task_lifecycle` (no bespoke completion path; run_config read-only in the loop); freezes splits after design (serial fan-out); strict-stops via `mark_phase_failed`. `multi_session` default unchanged. → decision_log (Run-ID).
- **iterate-2026-07-07-phase-gate-mode** (2026-07-07): Component — single-session pipeline SS2: new `gate_catalog.json` (SSoT, ~47 project/design/plan/build/deploy gates → `auto-default|orchestrator-approve|hard-stop`) + `lib/gate_policy.py` (validating loader/resolver/doc-gen) + `resolve_gate_policy.py` CLI. Additive/inert unless `run_config.mode==single_session`; constitution-locked gates never auto-answer. The 5 phase skills honor it via a block → `shared/prompts/single-session-gate-discipline.md`; `docs/gate-catalog.md` generated. → decision_log (Run-ID).
- **iterate-2026-07-07-single-session-mode-scaffold** (2026-07-07): Data-flow — single-session pipeline SS1 scaffold: run_config gains an additive optional `mode` (multi_session default | single_session; legacy→multi_session via `config_io.run_mode`) + `write-config --mode`; new `single_session/` package defines the phase-runner result contract + `.shipwright/run_loop_state.json` loop-state (pointers-only, reuses phase_task_lifecycle, never mutates run_config). No phase execution yet. → decision_log (Run-ID).
- **iterate-2026-07-06-grade-g6-projector-calibration** (2026-07-06): Component — shipwright-grade G6: projector recalibrated so well-run OSS repos no longer grade F (scorer UNCHANGED). Test-health keys on the CI-system app slug + merge-OR-PR-head rollup + a `has_test_infra` low-vs-n/a gate; new `lib/provenance_signal.py` gives change-traceability from the network PR-association ratio (git-log fallback); projector drops self-referential routes. Empirical gate asserts WELL-RUN > DEPRECATED (adds superpowers + agent-skills). → decision_log (Run-ID).
- **iterate-2026-07-06-diff-coverage-gate-hardening** (2026-07-06): Component — diff-coverage Phase-4 hardening: the warn-only CI gate DECISION moved from inline ci.yml shell into a TESTED entrypoint `measure_diff_coverage.py --fail-under` (new pure `lib/diff_coverage_gate.py::decide_gate`); it prints the report + exits FAIL(<80) / PASS / ERROR (no report → fail-closed, so a diff-cover crash can't green the gate). diff-cover pinned 10.3.0 + migrated to non-deprecated `--format`; real fail-path proven by a synthetic-repo integration test. Still warn-only. → decision_log (Run-ID).
- **iterate-2026-07-04-diff-coverage-grade-input-warn** (2026-07-04): Data-flow — diff-coverage Phase 3: the `diff_coverage.json` transient now feeds the Control-Grade **Test-Health** dim (not just the Phase-1 INFO line). New optional `GradeInputs.diff_coverage_percent` (default None → grade-neutral for the repo-agnostic grader); below 80% → ×0.85 penalty floored at imported `_grade_gate._BROKEN_BELOW` so it WARNs but never F-collapses (hard gate is Phase 4). Monorepo adapter only; grader unaffected. → decision_log (Run-ID).
- **iterate-2026-07-04-grade-report-audience-copy** (2026-07-04): Component — shipwright-grade HTML report reworked into a plain-language marketing instrument for non-experts: new render-only `lib/report_copy.py` (per-dimension plain question + concrete-scenario expandable + honest 'With Shipwright' upside, engine untouched); escape seam extracted to `lib/_html_dom.py`; cards show 'In your repo'/n-a reframe with the open-standard anchor + provenance moved into the expandable `<details>`; two-CTA funnel (Masterclass + adopt); honesty hedges pinned by tests. → decision_log (Run-ID).
- **iterate-2026-07-04-diff-coverage-rollout-combine** (2026-07-04): Data-flow — diff-coverage Phase 2: per-tier coverage (each plugin `scripts/` + `shared` + `integration`) is folded into one repo-relative `coverage.xml` by new `combine_coverage.py` (per-plugin `[paths]` remap). `record_coverage_total.py` writes the tracked repo-wide `coverage.total`=80.2%, lighting the dormant **W4** verifier green vs a new `shipwright_test_config.json.coverage.min`=70 anti-ratchet baseline. Non-gating (Phases 3–4). → decision_log (Run-ID).
- **iterate-2026-07-04-grade-g4-plugin-polish** (2026-07-04): Component — shipwright-grade G4: authoritative wiring (a healthy `.shipwright/` grades via `collect_all`→`build_grade_inputs`→the same `compute_grade` so grader-grade == dashboard-grade; corrupt/partial/stale/oversize → heuristic) + URL clone-and-grade behind `open_target()` on the `resolve_target` seam (scheme allowlist, shallow/no-submodule, ext/file transports off, non-interactive git, crash-safe tempdir; new read-surface: a cloned remote) + plugin registration at v0.29.1. → decision_log (Run-ID).
- **iterate-2026-07-04-grade-g3-html-report** (2026-07-04): Component — shipwright-grade G3: self-contained HTML report renderer (`lib/html_report.py` + `lib/_html_styles.py`) off the typed `report_model`, wired as `--format html`. Escape-by-default `el`/`_Raw` element builder + restrictive meta CSP + zero inline-JS/external-request surface + control/bidi stripping render UNTRUSTED repo strings inert; deterministic (timestamp-only footer), snapshot + parser-inertness tested. → decision_log (Run-ID).
- **iterate-2026-07-04-pr-review-exclude-generated-diff** (2026-07-04): Component — the Tier-3 PR-review gate (`plugins/shipwright-security/scripts/tools/pr_review.py`) now filters producer-generated file-sections out of the `gh pr diff` BEFORE the truncation check via new `scripts/lib/pr_review_diff_filter.py` (`filter_generated_paths`); a section is dropped only when EVERY path it touches is generated (rename-safe), and the excluded list is disclosed in the PR meta + comment. Stops medium+ iterates from tripping the size cap and losing their review. → decision_log (Run-ID).
- **iterate-2026-07-04-grade-g2-signals** (2026-07-04): Component — shipwright-grade G2 (campaign 2026-07-03-shipwright-grade): new signal modules light the maintainability, dependency, security + 3-tier test-health dims; the compliance engine gains one additive `GradeInputs.oversize_file_ratio` field + a dim-6 branch, byte-identical for existing inputs. Network enrichment (code-scanning SARIF / CI JUnit / Scorecard rollup) is behind `--allow-network`; untrusted CI JUnit XML is `defusedxml`-hardened. → decision_log (Run-ID).
- **iterate-2026-07-03-diff-coverage-measure-one-tier** (2026-07-03): Component — diff-coverage Phase 1: new `shared/scripts/tools/measure_diff_coverage.py` + a non-gating CI `diff-cover` step write % of CHANGED lines covered (vs origin/main, shared tier) to a gitignored transient `.shipwright/coverage/diff_coverage.json`; new read-surface consumed by `plugins/shipwright-compliance/scripts/lib/_diff_coverage_block.py` → a grade-neutral Test-Health INFO line. Tracked `coverage.total` + W4 deferred to Phase 2. → decision_log (Run-ID).
- **iterate-2026-07-03-grade-g1-projector** (2026-07-03): Component — new read-only plugin `plugins/shipwright-grade/` (campaign 2026-07-03-shipwright-grade, G1): projects a LOCAL git repo into `GradeInputs` and reuses `compute_grade` UNCHANGED (cross-plugin via `engine_bridge`, ADR-045-safe) to emit a deterministic A–F card; underivable dims render honest n/a. Reuses adopt detectors (audited read-only); hardened `git_exec` git seam; local-only, untrusted-input hardened. New read surface: a target repo's history + files. → decision_log (Run-ID).
- **iterate-2026-07-01-grade-composition-neutral** (2026-07-01): Component — Control Grade made composition-neutral: removed the self-relative FR-tag-decline penalty + verdict cap from `lib/_grade_gate.py` (and the now-dead `fr_tag_*` `GradeInputs` fields) so the feature-vs-maintenance work mix no longer caps or lowers the grade; the verdict caps only on dark-expected or broken pillars, and the `Recent changes traced to an FR` row is informational (INFO, never WARN). Traceability control = coverage + reconciliation + the write-time FR-gate. → decision_log (Run-ID).
- **iterate-2026-06-30-control-grade-honesty** (2026-06-30): Component — Goodhart-resistant Control Grade: new `lib/_grade_gate.py` (honesty layer) applies a self-relative FR-tag-decline penalty + a weakest-link verdict gate (decline / dark-expected-control / F-collapse caps) so the headline can't read "A — full control" while a load-bearing pillar decays; value model split to `lib/_grade_types.py`; anchors pivoted off DO-178C/IEC 62304 to single open SE/NIST standards (29148/12207/SSDF); new `.github/workflows/scorecard.yml` runs the native OpenSSF action. → decision_log (Run-ID).
- **iterate-2026-06-28-sbom-honesty** (2026-06-28): Data-flow — AR-04 SBOM honesty: the inventory resolves Python versions from each manifest's sibling `uv.lock` (+ a project-wide union fallback) and dedupes by installed version (duplicate `openai` row gone); licenses resolve across ALL `.venv`s so a stale per-manifest venv no longer drops a row to `-`. New read-surface `uv.lock`; new `collectors/_uv_lock.py`, `collectors/_venv_scan.py`, `sbom_render.py`; the ASCII verdict counts every package and never claims "all permissive" while any license is unresolved. → decision_log (Run-ID).
- **iterate-2026-06-28-ci-security-dashboard** (2026-06-28): Component + data-flow — AR-10: new producer `tools/refresh_ci_security.py` pulls the latest `security.yml` `findings.json` (via `github_api`) into a tracked, public-safe `.shipwright/compliance/ci-security.json`; new `lib/ci_security.py` renders the CI Security dashboard section + lights the Control-Grade Security dimension n/a→live (open high/critical; n/a — never a false CRITICAL — when un-ingested); `compliance_report` aux sections split to `lib/_dashboard_sections.py`. → decision_log (Run-ID).
- **iterate-2026-06-28-cc2-bp2-impact-producer** (2026-06-28): Component + data-flow — `work_completed` events gain an optional per-FR `fr_impact` map (`{FR-id: add|modify|remove|none}`) written by `record_event` + `finalize_iterate` (validated via shared `fr_classification.normalize_fr_impact`, read tolerantly by `WorkEvent`); new `plugins/shipwright-compliance/scripts/lib/_reconciliation.py` (SSoT for the grade + cc3 RTM) lights the Control-Grade change-reconciliation dimension n/a→live (touched-without-re-verify, age-neutral). → decision_log (Run-ID).
- **iterate-2026-06-28-cc1-bp1-fr-mapping** (2026-06-28): Component — new shared SSoT `shared/scripts/lib/fr_classification.py` (`is_traced`/`is_satisfied_no_fr`/`is_behavior_affecting`), shared by the `record_event` FR-gate and the compliance Control-Grade adapter + new `lib/_traceability.py`; WorkEvent gains `change_type`/`none_reason`/`spec_impact`; the gate blocks behavior-affecting no-FR changes and D1 uses all-time coverage. → decision_log (Run-ID).
- **iterate-2026-06-14-agent-doc-entry-budget-gate** (2026-06-14): Component — new SSoT `shared/scripts/lib/agent_doc_budget.py` + repo-agnostic CLI `tools/check_agent_doc_budget.py` + F11 verifier `check_agent_doc_budget` enforce the ≤600-char one-line agent-doc entry rule in EVERY repo (incl. adopted, via the plugin cache), closing the run-id-slug date hole that exempted the bold Learnings form; also fixes the `_append_architecture_update` blank-line writer. → decision_log (Run-ID).
- **iterate-2026-06-13-atomic-write-fsync-durability** (2026-06-13): Component — new shared durability primitive `shared/scripts/lib/atomic_write.py::durable_atomic_write` (tmp + `fsync` + `os.replace` + best-effort POSIX dir-fsync); ~20 atomic-write helpers across `shared/{lib,tools,hooks}`, `dev_server`, and 4 plugins delegate to it, closing the *lost-write* gap WP2 left open. Byte-identical output; fsync is the only behavioral change. External-review follow-up to `iterate-2026-06-13-runconfig-atomic-writes`. → decision_log (Run-ID).
- **iterate-2026-06-13-runconfig-atomic-writes** (2026-06-13): Component — new `run_config_store.py` centralizes atomic (tmp+os.replace) + path-coordinated-lock writes to `shipwright_run_config.json`; the orchestrator (`save_run_config`/`update_step`), `phase_task_lifecycle`, and `append_phase_history` writer families now coordinate by the canonical `*.json.lock` path (audit 2026-06-10 WP2: F11 unlocked/stale RMW, F12 torn read, F13 nested 30s timeout → outer 60s). → decision_log (Run-ID).
- **iterate-2026-06-10-phase-hook-lifecycle** (2026-06-13): Component — new shared `hook_session.py` resolves phase-hook identity (project_root + session_id) from the Claude-Code **stdin payload** (+`resolve_project_root()` fallback), not env vars no launcher sets (F1), so the v2 lifecycle engages from a bare launch card instead of no-op'ing. `record_event` gains `append_event_idempotent` (dedup scan + append in ONE `_FileLock`, F14) + first-class `phase_failed`/`stale_stop_rejected` event types (F15). (PR #224)
- **iterate-2026-06-12-cross-component-gate** (2026-06-12): Component — new `cross_component` risk flag (`CROSS_COMPONENT_FILE_PATTERNS`: merge/churn/event-log resolver, hooks + hook fan-out, pipeline validators, campaign drain) forces an INTEGRATION test (`category:"integration"` in the Ledger) at medium+. NON-dodgeable: F11 verifier `check_integration_coverage` recomputes the flag from the diff, not an agent-report, and STOPs without it. Closes the composition gap (empirical machinery was depth+breadth, not composition). (PR pending)
- **iterate-2026-06-12-delivery-watch** (2026-06-12): Component — new `shared/scripts/tools/watch_pr_delivery.py`: F11's final gate polls `gh pr view` until the PR is MERGED+green (delivered), a Required Check fails (STOP, exit 1), is closed, or times out — kills "shoot and forget" (armed ≠ done; #213 was reported done while CI was red). Pure `classify_delivery` + thin gh poll loop; companion F2 rule runs the iterate-plugin agent-doc budget lint (outside the `shared/tests` F0) before push. (PR pending)
- **iterate-2026-06-12-union-curated-agent-docs** (2026-06-12): Component — `merge=union` extended to the two curated agent-docs (architecture.md + conventions.md) via a distinct `CURATED_DOC_UNION_PATHS` category (`ALL_UNION_PATHS = UNION_PATHS + CURATED`; `UNION_PATHS` still the JSONL pin). Closes the curated-prose half of the cascade the regenerate resolver can't touch: union keeps both prepended bullets, honored server-side, so `integrate_main` no longer blocks on a curated-doc-only conflict. Self-heal path split to `gitattributes_selfheal.py` (bloat). (PR #213)
- **iterate-2026-06-12-arch-drift-test-scope** (2026-06-12): Data-flow — the two whole-set arch-drift checkers (Group-F **F5** detective + the `test_architecture_md_reflects_arch_impact` drift test) scope to drops event-owned by this tree (`events_log.finalized_run_ids` reads this tree's committed `shipwright_events.jsonl`; `architecture_doc.records_in_run_set` filters), failing open when no event log exists, so cross-branch campaign sibling drops in the shared main-rooted `decision-drops` dir no longer false-fail a later branch. The F11 gate was already single-run_id scoped. (PR #207)
- **iterate-2026-06-06-arch-drift-detector** (2026-06-06): Convention — architecture-drift is enforced by content reconciliation, not history-diffing: the Group-F **F5** detective + new F11 gate `check_architecture_documented` require every `architecture_impact` drop's run_id to appear in its target doc, sharing one oracle `shared/scripts/lib/architecture_doc.py`. → archive
- **iterate-2026-06-05-scanner-degraded-marker** (2026-06-05): Data-flow — a degraded scanner leg (fatal/empty/truncated `_run_tool` None-branch) now propagates via an OSSBackend `scan_errors` control-plane side-channel → `findings.json.degraded` → `scan.py` exit 2 → the monorepo `security.yml` critical-gate fails closed, instead of returning `[]` that was indistinguishable from a clean scan and passed green. The findings list stays pure (no synthetic critical finding; control-plane signal kept off the data-plane). (PR #157)
- **iterate-2026-06-05-fr-linkage-lifecycle** (2026-06-05): Convention — the FR-gate is enforced on the finalize write-path: `finalize_iterate._record_event` now calls the same `record_event._fr_or_change_type_gate_error` before `append_event` (after the idempotency early-return), fail-closed via `FinalizeGateError`; and Group-D **D3** counts a same-event `new_frs`+`affected_frs` as delivered (`ts >= promised_ts`, was strictly `>`). (commit 2b0fb66c, campaign C3)
- **iterate-2026-06-05-bloat-marker-worktree-aware** (2026-06-05): Convention — `bloat_baseline.strip_worktree_prefix()` lets `check_file_size` and the Stop-hook bloat gate strip the `.worktrees/<slug>/` prefix for the baseline membership/ceiling lookup, so a worktree iterate that bumped a baseline is no longer falsely blocked; the stored marker path keeps the prefix so the Stop gate can still re-measure the actual worktree file. (PR #150)
- **iterate-2026-06-05-b7-exclude-nonfunctional** (2026-06-05): Convention — `git_log_scan` Rule E excludes commits whose Conventional-Commit type is non-functional (`build`/`chore`/`ci`/`docs`/`style`/`test`) from the B7 "every commit has a matching event" detective; functional types (`feat`/`fix`/`perf`/`refactor`) are never excluded. Configurable via `b7_exclusions.exclude_nonfunctional_types` (default true) + `nonfunctional_types`. Supersedes the narrower Rule D. (PR #151)
- **iterate-2026-06-05-a5-gate-behavioral-probe** (2026-06-05): Component — compliance check **A5.8** extracts the deployed security gate's `run:` body and EXECUTES it against fixture scan output, asserting the ratified policy (critical→block, empty/invalid→fail-closed, clean→pass). Flavor-agnostic: each scenario stages BOTH `sarif/*.sarif` AND `findings.json`, so the probe is correct whether the gate reads SARIF (adopted repos) or `findings.json` (this monorepo). (PR #152)
- **Campaign `2026-06-05-track-triage-jsonl`** (2026-06-05): git-track `.shipwright/triage.jsonl` (anchor `trg-2fb7d3bc`) — sub-iterates iterate-2026-06-05-sbom-cluster-stable-identity, iterate-2026-06-05-triage-dismissed-gc (new `shared/scripts/tools/triage_gc.py`), iterate-2026-06-05-triage-track-c1-gitignore (gitignore negation + scaffolder self-heal), iterate-2026-06-07-triage-main-tree-reconcile (`reconcile_triage.py` folds main-tree drift into one B7-exempt `chore(triage)`). → archive
- **iterate-2026-06-03-campaign-status-field** (2026-06-03): Data-flow — producer-owned campaign lifecycle: `status.json` + `campaign.md` frontmatter gain a `draft→active→complete` `status` field (`campaign_progress.LIFECYCLE_STATUSES`); optional, legacy-fallback to derived `done<total`. New write-surface: the `status` key. Anchor `trg-f06f04e3`. → archive
- **iterate-2026-06-10-status-projection** (2026-06-10): Data-flow — new pure lib `shared/scripts/lib/campaign_status.py` projects a campaign's `status.json` from the tracked event log (`campaign.md` skeleton authoritative; never-downgrade merge over committed status). Campaign `2026-06-07-tracked-campaign-status` S2. Read-surface: `shipwright_events.jsonl`. → archive
- **iterate-2026-06-10-finalize-resolver** (2026-06-10): Data-flow + component — a campaign's `status.json` becomes durable/tracked/per-tree: F5b re-projects + writes it (F6 stages it → ships in the PR); the churn resolver re-projects ONLY conflicted campaigns. New lib `shared/scripts/lib/campaign_status_io.py`. Campaign `2026-06-07-tracked-campaign-status` S3. → archive
- **iterate-2026-06-02-sessionstart-dedup-guard** (2026-06-02): Convention — new shared primitive `shared/scripts/lib/event_once.py::claim_once` (atomic O_EXCL first-wins, TTL-armed, fail-open) lets one of the N per-plugin SessionStart invocations do an expensive once-per-event action; applied to the Phase-Quality Tier-1 FAIL injection (was emitting ~12×). Interim fix before campaign `2026-06-02-hook-consolidation`. → archive
- **ADR-021** (2026-05-03): Adopt scaffolds .env.local with profile + framework keys (Layer-3 SSoT)
- **iterate-2026-05-30-gitignore-canon-propagation** (2026-05-30): Convention — the canonical `.shipwright/` artifact-ignore block has one SSoT `shared/templates/shipwright-gitignore.template`; new `shared/scripts/lib/gitignore_canon.py` line-merges missing rules into a target `.gitignore` (adopt Step E.6 + project `--status complete`). Template↔framework congruence pinned by `test_gitignore_template_congruent.py`. → archive
- **ADR-024** (2026-05-03): Boundary Tests Foundation — `touches_io_boundary` risk flag + Boundary Probe sub-step in iterate Build TDD (Sub-Iterate A of campaign iterate-skill-hardening). New helper `is_io_boundary_change(changed_files)` in `plugins/shipwright-iterate/scripts/lib/classify_complexity.py`; new reference docs `references/boundary-probes.md` (8 edge-case categories) and `references/round-trip-tests.md` (producer→file→consumer test pattern). 7th Self-Review item ("Affected Boundaries") added.
- **ADR-032** (2026-05-05): Adopt writes shipwright_iterate_config.json with documented opt-out schema
- **ADR-034** (2026-05-06): load_review_config deep-merges per-project override; cascade helper added
- **iterate-2026-05-16-fix-events-worktree-aware** (2026-05-16): Data-flow — new SSoT `shared/scripts/lib/events_log.py::resolve_events_path` resolves `shipwright_events.jsonl` via `git rev-parse --git-common-dir` (superseded for the per-tree model by iterate-2026-05-29-events-jsonl-worktree-commit). Drift-pinned by `test_events_log_ssot.py`. → archive
- **iterate-2026-05-19-github-triage-importer** (2026-05-19): Component — new throttled SessionStart hook `import_github_findings.py` + `github_api.py` + `github_triage.py` import code-scanning / Dependabot / secret-scanning alerts + failed CI as `source=github` triage items. New write-surface `.shipwright/github_import_state.json`. Un-defers the ADR-047 CI producer (pull-based). → archive
- **iterate-2026-05-20-escape-md-cells** (2026-05-20): Component — new helper `shared/scripts/markdown_table.py::escape_cell` (top-level, NOT under `lib/`, per ADR-045) escapes `\`/`|`/newline in every event-derived markdown table cell the framework renders. Drift-pinned by `test_markdown_table.py` + a real-renderer round-trip. → archive
- **iterate-2026-05-23-security-adopt-compliance-snapshots** (2026-05-23): Component — extends the `Run-ID:`-snapshot producer set: adopt Step H (`adopt-<date>-<repo>` trailer), security Step 7.5 (`security-<scan_id>` refresh commit), and `update_compliance.PHASE_REPORTS` gains `adopt`+`security`. Convention: a new snapshot producer adds both the `Run-ID:` trailer and a `PHASE_REPORTS` entry. → archive
- **iterate-2026-05-23-compliance-md-single-producer** (2026-05-23): Component + data-flow — the 5 tracked compliance MDs are produced EXCLUSIVELY by iterate-finalize (Stop-hook auto-regen deleted); `audit_staleness.py` Group E becomes snapshot-provenance (latest `Run-ID:`-trailer commit touching `.shipwright/compliance/` vs on-disk) → zero E1-E5 false positives between iterates. → archive
- **iterate-2026-05-20-triage-launch-surface** (2026-05-20): Component — Triage Inbox redesigned as a launch-surface: per-repo/per-workflow **action-units** (not finding-mirrors), each with a `launchPayload`; new dedup prefixes `gh-security`/`gh-secrets`/`gh-ci`; new CLI `shared/scripts/tools/triage_cli.py`; `github_api.owner_repo()` local-first remote parse. ADR-057. → archive
- **iterate-2026-05-21-b1-compliance-dashboard-mode-aware** (2026-05-21): Mode-aware compliance dashboard. Detect adopted runs via `run_config.adoption` (corrects the plan's scope-based check). Adopted projects render pipeline phases as `n/a (adopted) INFO`; hide build-section and sections-reviewed rows for adopted. Add Why-warn 4th column to the compliance dashboard. Triage-open indicator surfaces open triage cards inline. See decision-drop `iterate-2026-05-21-b1-compliance-dashboard-mode-aware_001.json`.
- **iterate-2026-05-21-b2-sbom-polish** (2026-05-21): SBOM undeclared-license triage producer (per workspace). `emit_undeclared_triage()` in `sbom_generator.py` emits one `source='sbom'`, `kind='compliance'`, `severity='low'` item per manifest with undeclared packages; dedup-key `sbom:undeclared:<manifest-rel-path>`. See decision-drop `iterate-2026-05-21-b2-sbom-polish_001.json`.
- **iterate-2026-05-21-b3-test-evidence-layer-and-triage** (2026-05-21): Per-layer FAIL triage + Layer column + `record_event` layers schema. `emit_test_failure_triage()` emits one `source='test-evidence'` item per failing layer from the latest `test_run` event; dedup `test-fail:<layer>`; severity high for e2e/integration/pgtap, low for unit. New convention: `test_run` events carry first-class `integration` and `pgtap` keys alongside `unit` / `e2e` with optional `failed` counts. See decision-drop `iterate-2026-05-21-b3-test-evidence-layer-and-triage_001.json`.
- **iterate-2026-05-21-b4-rtm-deep-link-and-coverage** (2026-05-21): RTM consumes `frId` cross-link + actionable Coverage subsections. Requirements-coverage Status cell renders `FAIL → [trg-XXX](...#trg-XXX)` per open triage item with matching `frId` (overrides COVERED). Coverage Summary section gains three actionable subsections. See decision-drop `iterate-2026-05-21-b4-rtm-deep-link-and-coverage_001.json`.
- **iterate-2026-05-21-c1-fr-gate-finalize** (2026-05-21): Hard-enforce FR-or-change-type at iterate finalize (forward-only). New gate `_fr_or_change_type_gate_error` in `record_event.py` fires for every `work_completed`+`source=iterate` event. Pass conditions: `affected_frs`/`new_frs` non-empty OR `change_type ∈ {docs, tooling, compliance, infra}`. Convention: every iterate event must link to an FR or declare why it doesn't. See decision-drop `iterate-2026-05-21-c1-fr-gate-finalize_001.json` (ADR-059).
- **iterate-2026-05-21-c2-architecture-and-adr-drift-detector** (2026-05-21): F4–F7 detective-only documentation hygiene checks. Added F4 (ADR > 60 lines without `spec_ref`), F5 (architecture marker vs arch-impact drops via `git log`), F6 (`CLAUDE.md` > 200 lines), F7 (`CLAUDE.md` Iterate-annotation count > 5) to `group_f.py`. All four are detective-only — Phase-Quality can't see them, only a holistic scan can. See decision-drop `iterate-2026-05-21-c2-architecture-and-adr-drift-detector_001.json`.
- **iterate-2026-05-21-c3-plugin-cache-sync-check** (2026-05-21): Detective-only plugin-cache vs repo drift check. New standalone Python script `scripts/check_plugin_cache_sync.py` walks `plugins/shipwright-*` in the repo and compares each against the lexically-latest version dir under `~/.claude/plugins/cache/shipwright/`. Convention: after every plugin-side edit + `git push`, operators MUST run `bash scripts/update-marketplace.sh`; this script is the drift detector. See decision-drop `iterate-2026-05-21-c3-plugin-cache-sync-check_001.json`.
- **iterate-2026-05-21-triage-producer-contract** (2026-05-21): Triage producer contract — schema + RTM-link fields + inbox polish. New wire SSoT `shared/schemas/triage_item.schema.json`; optional `frId`/`suiteId`/`eventId` append-event keys for RTM deep-link; `aggregate_triage.py` emits HTML anchors per card. New convention: every producer that appends a triage item must validate against the schema. See decision-drop `iterate-2026-05-21-triage-producer-contract_001.json`.
- **iterate-2026-05-22-deterministic-render-timestamps** (2026-05-22): Data-flow — new `shared/scripts/lib/events_log.latest_event_dt()` returns `max(event.ts)`; every framework-rendered banner consumes it instead of `datetime.now()`, so re-renders against the same event log are byte-identical. ADR-070. → archive
- **iterate-2026-05-23-iterate-f7-tracked-event-log-commit** (2026-05-23): Component — new F7b step `shared/scripts/tools/commit_event_followup.py` seals a tracked-dirty `shipwright_events.jsonl` after F7 (worktree-aware, idempotent) so a later `git reset --hard` can't wipe the event. Legacy/out-of-band only under the per-tree model. ADR-073. → archive
- **iterate-2026-05-23-verifier-multi-commit-aware** (2026-05-23): Component — the F11 verifier resolves the F7 event by `run_id` (`_find_work_event_by_run_id`), not HEAD commit, since `commit_hash` drifts across multi-commit iterates/rebases; the substring search stays a back-compat fallback. ADR-076. → archive
- **iterate-2026-05-23-verifier-drift-remediation** (2026-05-23): Convention — new `shared/tests/test_architecture_md_reflects_arch_impact.py` enforces that every `architecture_impact ∈ {component,data-flow,convention}` drop's run_id appears in its target doc; RED→GREEN backfilled 11 missing entries. F2's coupling is now structural. ADR-075. → archive
- **sub_iterate-20260525-211635-B8** (2026-05-26): Component — new `shared/contracts/` cross-plugin facade: `shared.contracts.compliance` + `shared.contracts.iterate` re-export the supported entry points (sys.path bootstrap once); adopt + test consumers use them instead of subprocess/ancestor-walk. Future splits MUST keep the re-exported names importable. ADR-088. → archive
- **iterate-2026-05-24-sbom-triage-cluster-collapse** (2026-05-24): Convention — the SBOM undeclared-license triage producer collapses N≥2 workspaces sharing a `(sorted_undeclared_names, manifest_type)` signature into ONE cluster action-unit `sbom:undeclared-cluster:<sha256>` (membership-encoded key auto-dismisses on drift). ADR-082. → archive
- **ADR-055** (2026-05-19): GitHub findings triage producer (un-defers the CI producer)
- **ADR-068** (2026-05-21): Artifact-based GitHub security producer for Triage Inbox
- **ADR-078** (2026-05-26): Split dev_server.py 997 LOC into 10-file package; preserve shim for uv run callers
- **ADR-088** (2026-05-26): shared/contracts/* — cross-plugin contract surface introduced for compliance + iterate
- **iterate-2026-05-25-bloat-defense** (2026-05-25): Component (ADR-083) — Campaign A defense-in-depth: local pre-commit anti-ratchet (`scripts/hooks/pre-commit` + `install-hooks.{sh,ps1}`), PR-time `bloat-check.yml`, shared `anti_ratchet.py`, the bloat-exception ADR template, and the `shared/glossary.md` registry. Constitution §21 extended with the anti-ratchet rule. → archive
- **iterate-2026-05-25-bloat-review** (2026-05-25): Component (ADR-085) — Campaign A closure: the Bloat Checklist appended verbatim to both reviewer prompts (byte-parity pinned by `test_reviewer_bloat_checklist_parity.py`); new compliance audit **Group H** (`group_h.py`, 7 checks H0-H6) reusing the producer-side `bloat_baseline.scan`. → archive
- **iterate-2026-05-30-reviewer-stack** (2026-05-30): Component (ADR-102) — `/shipwright-build` Step 6 gains a 3-stage cascade `spec-reviewer` (HARD-GATE) → `code-reviewer` → conditional `doubt-reviewer`; orchestration in `references/code-review.md`, the Kern carries a pointer; reviewers stay internal. Drift: `test_reviewer_orchestration.py`. → archive
- **Campaign B1 — SKILL.md modular references** (2026-05-26): Component (ADR-074) — 7 oversize SKILL.md files split to a ≤300-LOC Kern + per-topic `references/*.md`; test-locked anchors (Risk Taxonomy, Override Classes, Phase Matrix, named Steps) stay inline. New convention: Kern ≤300 LOC, deep dives offloaded to `references/`. → archive
- **Campaign B2 — collectors/ package** (2026-05-26): Component — `plugins/shipwright-compliance/scripts/lib/data_collector.py` (1559 LOC) split into per-domain `collectors/` modules + a 41-LOC re-export shim; all 5 compliance MDs regenerate byte-identical. → archive
- **Campaign B3 — phase_quality/ package** (2026-05-26): Component — `shared/scripts/lib/phase_quality.py` (1108 LOC) split into 9 thematic submodules (re-export `__init__`); sibling diff added the Group-H bloat column to the Compliance Dashboard. → archive
- **Campaign B5 — orchestrator_pkg/** (2026-05-26): Component — `plugins/shipwright-run/scripts/lib/orchestrator.py` (983 LOC) split into `orchestrator_pkg/` (12 submodules) + a 41-LOC shim preserving the `mocker.patch` targets and the `write-config|get-next-step|update-step` CLI. → archive
- **Campaign B6 — github_triage/ package** (2026-05-26): Component — `shared/scripts/github_triage.py` (929 LOC) replaced by the `github_triage/` package (every submodule ≤300 LOC); the public import surface (12 names + `SOURCE`) preserved exactly. → archive
- **iterate-2026-05-27-tracked-artifacts-single-producer-and-finalize-sandbox** (2026-05-27): Component + data-flow (ADR-089/090) — extends single-producer to the agent-doc trio (`session_handoff`/`build_dashboard`/`triage_inbox`): Stop hooks write live state to gitignored `.shipwright/agent_docs/runtime/`, iterate-finalize is the sole tracked producer; finalize hard-gated when the session→worktree pointer is None. → archive
- **iterate-2026-05-27-guide-readme-refresh** (2026-05-27): Convention — docs-only refresh of `docs/guide.md` + `README.md` to the post-v0.22.0 state (8 audit groups, 300/400-LOC budgets, runtime/snapshot split, merge-not-rebase, ADR spec folder). No new convention introduced. → archive
- **iterate-2026-05-29-events-jsonl-worktree-commit** (2026-05-29): Data-flow + component (ADR-094) — `shipwright_events.jsonl` is now a per-tree, PR-committed artifact: `resolve_events_path` returns `project_root/EVENT_FILE` literally; the `work_completed` event is recorded in the worktree's own log at F5b, staged by F6, ships in the PR. F6.5/F7/F7b skipped in the worktree flow. → archive
- **iterate-2026-05-29-skill-bootstrap-pack** (2026-05-29): Component (ADR-097) — Skill Bootstrap Pack: SessionStart `session_start_using_shipwright.py` injects `using-shipwright.md`; a PostToolUse→Stop wave (`mark_plugin_edit.py` + `plugin_sync_reminder_on_stop.py`) surfaces plugin-cache drift as `source=plugin-sync` triage. Hooks registered across all 12 plugins (forward/reverse meta-test). → archive
- **iterate-2026-05-31-ci-gate-guard** (2026-05-31): Component (ADR-108) — new `check_ci_gate_coverage.py` (+ `ci_gate_scan.py` / `ci_gate_allowlist.py`) gates `ci.yml`: fails on an unreferenced test dir, an undocumented loose gate (`|| true` / `continue-on-error`), or a non-fail-closed security critical-gate. Allowlist has both-direction drift protection. → archive
- **ADR-115** (2026-05-31): plugin-sync Stop-hook triage item targets the durable main-repo log
- **ADR-121** (2026-06-03): Producer-owned campaign lifecycle status (draft -> active -> complete)
- **ADR-124** (2026-06-05): A5.8 behaviorally probes the deployed critical-gate
- **ADR-131** (2026-06-05): Degraded scanner legs propagate via a scan_errors side-channel, not synthetic findings
- **ADR-133** (2026-06-05): Machine-churn-only triage GC tool
- **ADR-139** (2026-06-08): Gitignored per-tree triage outbox + union reader
- **ADR-140** (2026-06-08): Sweep triage outbox into PR branch; GC only origin-delivered lines
- **iterate-2026-06-10-triage-dedup-keep-last-append** (2026-06-10): Data-flow — `churn_merge.dedup_triage_lines` collapses same-id `append` events keeping the LAST (mirrors the append-log reader reduction), so a re-appended updated finding no longer wedges the outbox sweep as a `duplicate append`. Campaign `2026-06-08-triage-outbox-delivery` follow-up. → archive
- **iterate-2026-06-12-triage-status-idle-main-outbox** (2026-06-12): Data-flow — `triage.mark_status` routes an idle-main status flip (dismiss/snooze/promote) to the outbox (`should_route_to_outbox`), symmetric with `append_triage_item`; elsewhere residence-derived (TRACKED-PREFERRED). Completes campaign `2026-06-08-triage-outbox-delivery` D1. ADR-100 file. → archive
- **iterate-2026-06-12-automerge-serial-integrate** (2026-06-12): Component — new `shared/scripts/tools/ensure_current.py` (thin wrapper over `integrate_main`) is the F11 / campaign "refresh-if-behind" guard fixing the auto-merge churn cascade (Option A): GitHub's server-side 3-way merge can't run the regenerate-at-merge resolver, so a behind branch merges stale or stalls DIRTY on regenerated snapshots. F11 brings the branch current THROUGH `integrate_main` before arming `gh pr merge --auto`; campaigns set `SHIPWRIGHT_ITERATE_AUTOMERGE=0` to drain PRs serially. → decision_log (Run-ID).
- **iterate-2026-06-13-code-simplify-skill** (2026-06-13): Component — new `plugins/shipwright-iterate/scripts/lib/behavior_snapshot.py` (snapshot/verify gate) records the green test-state (collected node-id set + counts + exit + source LOC) at the gitignored `.shipwright/runs/<run_id>/behavior_snapshot.json` and STOPs a simplify on behavior drift or removed coverage; new SIMPLIFY sub-mode of CHANGE (classify_intent `mode`) routes through `references/F-simplify.md` (OS1). → decision_log (Run-ID).
- **iterate-2026-06-13-unify-simplify-reducibility** (2026-06-13): Component — RELOCATED the behavior_snapshot gate to **`shared/scripts/tools/behavior_snapshot.py`** (SSoT; supersedes the OS1 entry's `plugins/.../scripts/lib/` path) so the shared reducibility catalog can cite it without an inverted plugin→shared dep. Unifies the simplify gate + bloat catalog: F-simplify adopts the D·A·X·C·S·M·P·T vocabulary; the catalog cites it as the mechanical G3 ("keeps-tests-green") proof on exec surfaces (CI Tier-3 exempt). → decision_log (Run-ID).
- **iterate-2026-07-10-persist-session-plan** (2026-07-10): Data-flow — `classify_complexity.main() --run-id` additively persists a session plan (`session_plan.build_session_plan` → `{run_id,complexity,risk_flags,phases,skips}`) to the GITIGNORED `.shipwright/agent_docs/iterates/<run_id>.plan.json` for the WebUI scoped Plan-Card; stdout stays byte-identical, persist is fail-soft, and `complexity_history.load_history_prior` now skips `*.plan.json` so the co-tenant plan never counts as a finalized history entry. → decision_log (Run-ID).
- **ADR-151** (2026-06-07): Reconcile-and-commit main-tree triage.jsonl drift in tooling
- **ADR-160** (2026-06-10): Per-tree campaign status.json: finalize wiring + scoped churn resolver
- **ADR-161** (2026-06-10): Project campaign status from the event log (never-downgrade)
- **ADR-163** (2026-06-10): Triage dedup collapses same-id appends keep-last (reader parity)
- **ADR-166** (2026-06-11): gh-pr-ci producer: failed hard-gates on open PRs -> triage
- **ADR-173** (2026-06-12): Event-ownership scoping for whole-set arch-drift checkers
- **ADR-174** (2026-06-12): Serial integrate_main merge for campaign/parallel iterates (auto-merge churn fix, Option A)
- **ADR-181** (2026-06-12): cross_component risk flag forces integration coverage (non-dodgeable)
- **ADR-182** (2026-06-12): Delivery-Watch: delivered = merged + green (no shoot-and-forget)
- **ADR-189** (2026-06-12): mark_status routes idle-main status flips to the outbox (completes D1)
- **ADR-191** (2026-06-12): merge=union for curated agent-docs (close the structural gap)
- **ADR-197** (2026-06-13): Phase hooks resolve identity from stdin payload; atomic event dedup; failure event types
- **ADR-199** (2026-06-13): Shared durable_atomic_write primitive for all atomic writers
- **ADR-204** (2026-06-13): Atomic + path-coordinated run_config writes
- **ADR-212** (2026-06-13): Behavior-preserving SIMPLIFY sub-mode + snapshot/verify gate
- **ADR-217** (2026-06-13): Unify simplify <-> reducibility around one shared tool + one catalog
- **ADR-221** (2026-06-14): Repo-agnostic agent-doc entry-budget gate + cleanup
- **iterate-2026-07-10-grade-snapshot-events** (2026-07-11): Data-flow — grade_snapshot appended to the durable tracked shipwright_events.jsonl at each compliance grade regen (record_event new --type + emit_grade_snapshot), giving the WebUI Ship's-Log grade trend + per-run delta (M-Pre-3). → decision_log (Run-ID).
- **iterate-2026-07-10-run-brief-intake** (2026-07-11): Data-flow — /shipwright-run accepts a WebUI-wizard brief (file/payload) via a tested brief_intake helper that maps persistence→profile + run-location→deploy/env and asks only the still-missing questions; no brief → legacy interview unchanged (K2c). → decision_log (Run-ID).
- **iterate-2026-07-14-sweep-drift-dismiss-loss** (2026-07-14): Component — the D2 outbox sweep gains a main-tree drift repair (`sweep_drift.py`; leaf `sweep_text.py`; reporting `sweep_result.py`). New write surface: the sweep writes MAIN's tracked `.shipwright/triage.jsonl` — it adopts append-only drift there into the outbox so appends that reached no branch ride the iterate PR, and `decide()` gains a `known_append_ids` universe so a legitimate status is never quarantined. → decision_log (Run-ID).
- **iterate-2026-07-15-tag-convention-and-manifest** (2026-07-15): Data-flow — new `test_links` compliance collector emits `.shipwright/compliance/test-traceability.json` (schema v2), the backward test→FR link + per-layer join built from `@FR` tags across pytest/Playwright/Vitest; wired into `update_compliance` PHASE_REPORTS. Consumed next by the layer-aware RTM (TT2). → decision_log (Run-ID).
- **iterate-2026-07-15-execution-evidence** (2026-07-16): Component + data-flow — per-test execution-evidence reader as the R1 coverage source. → decision_log (Run-ID)
- **iterate-2026-07-18-outbox-newline-corruption** (2026-07-18): Component — record-boundary integrity for the append-only triage log. New neutral leaf `lib/jsonl_records.py` owns where a record ends (writer newline probe + partial recovery of concatenated records); `lib/triage_header.py` takes header bootstrap out of `triage.py`. New `tools/triage_repair.py` CLI repairs corrupted lines on disk (quarantine-before-replace, `--writers-quiesced`, minimal rewrite preserving EOL). The reader no longer drops a whole line, so an operator dismissal is not silently lost. → decision_log (Run-ID).
- **iterate-2026-07-18-events-jsonl-record-boundary** (2026-07-18): Component — extends the `lib/jsonl_records.py` record-boundary contract from the triage log to the AUDIT TRAIL: `record_event.append_event(_idempotent)` probe the newline before appending, `lib/config.read_events` recovers concatenated records instead of dropping the line, and the lock-free adopt `event_seeder` carries a documented duplicate probe (ADR-045 blocks importing the leaf). `merge=union` makes concatenation reachable by an ordinary merge, so recovery is the load-bearing half. → decision_log (Run-ID).
- **iterate-2026-07-20-one-header-driven-parser** (2026-07-20): Component — ONE header-driven FR-table reader (`lib/fr_table_reader.py` + neutral leaf `lib/_fr_table_cells.py`) replaces five parsers; each caller keeps only its return TYPE as a projection. Revises ADR-031 (premise falsified) and flips FV-1/3/4/5; detail in ADR-107. → decision_log (Run-ID).
- **iterate-2026-07-19-requirements-merge-catalog** (2026-07-19): Component — ONE requirements catalog: change history leaves the requirement (417→286 lines, same 15 ids) and becomes an event-log query; each requirement emits an EXPLICIT `<a id="fr-01NN"></a>` anchor because the RTM links `#fr-0101` and the viewer matches exactly. New neutral module `audit/_group_d_link_proof.py`. Flips FV-2; I4 dedup goes global. Detail in ADR-109. → decision_log (Run-ID).
