# Iterate Spec — Adopt Automerge-Readiness Pack (CodeQL + AUTOMERGE_SETUP)

- **Run ID:** iterate-2026-06-13-adopt-automerge-readiness
- **Intent:** FEATURE (adopt scaffolding extension)
- **Complexity:** medium
- **Branch:** iterate/adopt-automerge-readiness
- **Spec source:** `Spec/early-access-readiness-plan.md` §B4 / §B4.5; triage anchor `trg-a678bd00`
- **Spec Impact:** ADD (new templates + scaffolders; no FR-table change — framework-internal tooling)

## Problem

`/shipwright-adopt` scaffolds `ci.yml` + `security.yml` + `claude-review.yml` +
`.gitleaks.toml`, but **not** `codeql.yml`, **not** `bloat-check.yml`, and **no
branch-protection setup guidance**. A freshly adopted repo therefore has the
workflows behind only 3 of the 6 Required-Check job-name families the monorepo
uses for automerge, and the adopter has no instructions to wire branch
protection. Without that, B4.5-style automerge cannot be turned on for a
brownfield repo.

## Scope (this iterate) — CodeQL + AUTOMERGE_SETUP

Decided via scoping question (2026-06-13): **defer bloat-check**, ship a
fully-working CodeQL + branch-protection-guidance deliverable now.

1. **`shared/templates/github-actions/codeql.yml.template`** — dormant
   (`workflow_dispatch:` only, Phase-B activation discipline), language matrix
   **parametrized by profile** via a `${SHIPWRIGHT_CODEQL_LANGUAGES}` placeholder
   the scaffolder renders. `continue-on-error: true` on the analyze step (so the
   `Analyze (<lang>)` job is green on a private repo without GHAS — mirrors the
   monorepo codeql.yml + the security.yml SARIF-upload guard).
2. **`shared/templates/AUTOMERGE_SETUP.md.template`** — profile-aware doc landing
   at repo root. Lists the **actually-scaffolded** Required-Check job names
   (derived from the deployed workflow files, matrix-expanded), step-by-step
   branch-protection UI guidance, `Allow auto-merge` setting, and the
   `gh pr merge --auto --squash` pattern. Documents the deferred bloat-check as a
   manual/monorepo-dev opt-in, and the free Path-A vs CodeQL/GHAS Path-B choice.
   **Omits the `Require signed commits` setting** (spec line 948 — headless
   iterate PRs are unsigned; requiring signing would silently block automerge).
3. **Adopt wiring:** convention locks (`shared/scripts/lib/codeql_workflow.py`,
   `shared/scripts/lib/automerge_readiness.py`), two scaffolders
   (`codeql_workflow_scaffolder.py`, `automerge_setup_scaffolder.py`),
   orchestrator calls in `generate_adoption_artifacts.py` (CodeQL after CI; the
   doc LAST, after every workflow scaffold so it reads real job names),
   SKILL.md Step E + Step C note, `references/artifact-templates.md` slots.
4. **Docs:** `docs/hooks-and-pipeline.md` artifact-write matrix +
   `docs/security-ci-setup.md` (CodeQL now scaffolded / Path-B cross-ref).

### Out of scope (deferred to follow-up)

- `bloat-check.yml.template` + vendoring of the anti-ratchet runner into adopted
  repos (the monorepo workflow calls `shared/scripts/hooks/anti_ratchet_check.py`,
  absent in adopted repos — needs a vendoring story). New triage card filed.
- Automatic branch-protection config via `gh api` — DOC-only by design (never
  mutate user GitHub settings unasked).
- WebUI `claude-review.yml` → OpenRouter migration (separate iterate).

## Acceptance Criteria

- **AC1** CodeQL template exists, is dormant (no active `pull_request`/`push`),
  carries `workflow_dispatch`, explicit `permissions` (incl.
  `security-events: write`), `continue-on-error` on analyze, and the
  `${SHIPWRIGHT_CODEQL_LANGUAGES}` placeholder; drift test pins it to the
  convention lock.
- **AC2** CodeQL scaffolder renders the correct language list per profile
  (`python-plugin-monorepo`→`[python]`, `supabase-nextjs`/`vite-hono`→
  `[javascript-typescript]`), never overwrites, distinct reason codes for
  `already_exists` / `no_codeql_for_profile` / `profile_unresolved`; rendered
  output is valid YAML.
- **AC3** `required_check_names(project_root)` derives matrix-expanded check
  names from the deployed workflow files; for each of the 3 profiles the names
  match what the scaffolded ci/security/codeql/claude-review workflows actually
  declare (defensive: wrong names → branch protection silently never matches).
- **AC4** AUTOMERGE_SETUP scaffolder renders the doc with the correct per-profile
  job names + the "activate triggers FIRST, then require the job" instruction;
  never overwrites a pre-existing file.
- **AC5** Orchestrator wires both; the doc scaffold runs LAST and reads the
  real (possibly pre-existing) workflow files. Pipeline + SKILL + docs updated.

## Affected Boundaries (`touches_io_boundary`, `touches_shared_infra`)

- **Producer:** scaffolders write `.github/workflows/codeql.yml` (rendered YAML)
  + `AUTOMERGE_SETUP.md` (rendered markdown) into target repos.
- **Consumer:** the doc renderer PARSES deployed `.github/workflows/*.yml`
  (round-trip: template → rendered file → parsed-back check names).
- **Convention-lock SSoT:** `codeql_workflow.py`, `automerge_readiness.py` —
  drift tests pin templates ↔ constants.

## Confidence Calibration

- **Boundaries touched:** GitHub-Actions YAML templates (write) + workflow-file
  parsing (read) + profile→language SSoT + profile→check-name derivation +
  markdown doc render.
- **Empirical probes run:**
  - CodeQL drift test → 23 green (dormant triggers, `${SHIPWRIGHT_CODEQL_LANGUAGES}`
    placeholder, permissions floor, `continue-on-error` all verified against the
    real template).
  - Scaffolder render→parse round-trip: rendered codeql.yml parses back with
    `matrix.language == profile langs`; placeholder fully substituted.
  - `required_check_names` vs deployed workflows: derived names == parsed names
    for all 3 profiles (the defensive "wrong name silently never matches" guard).
  - Real-orchestrator E2E (`test_full_pipeline_e2e_via_subprocess`, slow) →
    `generate_adoption_artifacts` writes codeql.yml + AUTOMERGE_SETUP.md with
    correct payloads; doc lists `Analyze (javascript-typescript)` + `Shipwright
    Security Scan`.
  - Full shared suite (3392 passed) incl. path-canon + hygiene meta-tests; ruff
    `0.15.15` green on all new/edited Python.
- **Test Completeness Ledger** (testable ⇒ tested; 0 untested-testable):

  | Behavior (AC) | Disposition | Evidence |
  |---|---|---|
  | AC1 codeql template dormant + placeholder + permissions + continue-on-error | tested | `test_codeql_workflow_convention.py` (23) |
  | AC2 codeql scaffolder renders per-profile langs; never-overwrite; reason codes (scaffolded/already_exists/no_codeql_for_profile/profile_unresolved) | tested | `test_codeql_workflow_scaffold.py` (17) |
  | AC2 rendered codeql is valid YAML + dormant | tested | `test_codeql_workflow_scaffold.py::test_rendered_matrix_languages`, `::test_rendered_is_dormant`, convention `::test_rendered_template_is_valid_yaml` |
  | AC3 check-name expansion (interpolate / no-name→job-id / no-ref→append-combo / multi-dim / include-exclude) | tested | `test_automerge_check_names.py::TestExpandCheckNames` (9) |
  | AC3 dormant detection | tested | `test_automerge_check_names.py::TestIsDormant` (3) |
  | AC3 `if:`-gated deploy jobs excluded from requireable + surfaced as conditional (review H1) | tested | `::test_required_checks_exclude_if_gated_deploy_jobs`, `::test_render_warns_about_conditional_deploy_jobs` |
  | AC3 include/exclude not dims (review M1); partial multi-dim appends full combo (review M2) | tested | `test_automerge_check_names.py::test_include_excluded_with_constant_name`, `::test_partial_multidim_appends_full_combo` |
  | AC3 derived names == deployed workflow names (3 profiles) | tested | `::test_required_check_names_match_deployed_workflows` |
  | AC3 KNOWN_WORKFLOWS drift-pinned to convention modules | tested | `::test_known_workflows_match_convention_modules` |
  | AC4 doc render: profile + table substituted, dormant-trap + signing-omit prose, dormant/active flags | tested | `::test_render_automerge_setup_substitutes_everything` (3); `test_automerge_setup_scaffold.py` (13) |
  | AC4 doc scaffolder never-overwrite + degenerate no-workflows repo | tested | `test_automerge_setup_scaffold.py` |
  | AC5 orchestrator wiring (codeql after CI; doc LAST; reads real files) | tested | `test_adopt_pipeline_subprocess.py::test_full_pipeline_e2e_via_subprocess` (slow) |
  | AC5 SKILL/reference cross-links resolve | tested | `test_cross_links.py`, `test_skill_references_link.py` |

  No `untestable` rows — every behavior introduced is covered.
- **Confidence-pattern check:** asymptote = render→parse round-trip across all 3
  profiles + real-orchestrator subprocess E2E; coverage = dormant triggers,
  permissions, continue-on-error guard, never-overwrite, all reason codes,
  matrix-expansion edge cases, no-workflow degenerate. No `cross_component`
  framework machinery touched (leaf producers under `shared/templates`,
  `shared/scripts/lib`, adopt `lib`; not merge/hook/phase-validator/campaign
  patterns) → no integration-coverage gate (confirmed against
  `classify_complexity.CROSS_COMPONENT_FILE_PATTERNS`).
