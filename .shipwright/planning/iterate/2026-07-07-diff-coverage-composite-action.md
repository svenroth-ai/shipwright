# Iterate spec — diff-coverage composite action (Stage 1)

- **Run ID:** `iterate-2026-07-07-diff-coverage-composite-action`
- **Intent:** CHANGE (Path B) — structural DRY refactor of the diff-coverage gate.
- **Complexity:** medium (override ↑ from history-prior `small`; blast radius = all
  consumers via `@main`, security-relevant action tag, multiple CI templates + their
  drift-protection meta-tests).
- **Spec Impact:** NONE (behavior-preserving) — the *delivered gate behavior* (warn-only,
  `diff-cover@10.3.0`, `--fail-under=80`, `--compare-branch=origin/main`, ubuntu-only) is
  **byte-identical** (proven empirically); only the *definition site* moves from inline
  template steps to a single consumed composite action. No FR touched (CI infrastructure) →
  F5b No-FR branch (`change_type: infra`).
- **Durable plan:** `.shipwright/planning/iterate/campaigns/diff-coverage/composite-action-refactor-plan.md`

## Problem
The diff-coverage gate is 3 hand-maintained copies (monorepo wrapper; WebUI ci.yml #205;
adopt templates #335). No single source of truth → the copies drift and framework
updates don't flow to consumers.

## Goal (Stage 1 only)
ONE central composite action in the monorepo that the adopt templates consume via
`uses:`. Updates flow to all consumers. Stage 1 is independently mergeable + non-breaking
(templates are dormant; gate stays warn-only).

## Scope — this iterate (Stage 1)
1. **Create** `.github/actions/diff-coverage-gate/action.yml` (composite):
   - inputs: `coverage-files` (required, space-separated cobertura paths),
     `compare-branch` (default `origin/main`), `fail-under` (default `80`),
     `diff-cover-version` (default `10.3.0`).
   - steps: SHA-pinned `astral-sh/setup-uv` → bash step that fetches the base branch
     and runs `uvx diff-cover@<version> <files> --compare-branch --fail-under`.
   - **Hardening:** inputs reach the shell via `env:` (`$INPUT_*`), NOT via
     `${{ inputs.* }}` interpolation in the `run:` body (closes the Actions
     expression-injection lint class).
   - The action is the **GATE only**; coverage PRODUCTION (vitest → cobertura) stays
     repo-specific. WARN-vs-HARD is the caller's step `continue-on-error` (action neutral).
   - Caller must checkout with `fetch-depth: 0` (documented in the action description).
2. **Refactor** both vitest adopt templates' `diff-coverage` job: replace the inline
   `Install uv` + `Diff coverage` steps with a single
   `uses: svenroth-ai/shipwright/.github/actions/diff-coverage-gate@main` step passing
   `coverage-files`. Keep checkout(fetch-depth:0) + node + test-with-coverage steps,
   `continue-on-error: true`, `runs-on: ubuntu-latest`, `if: pull_request`.
3. **Update** `shared/tests/test_ci_template_diff_coverage.py`: the job now asserts a
   `uses:` step referencing the action (not the inline `diff-cover@10.3.0` run body);
   keep warn-only + ubuntu-only assertions.
4. **Add** `shared/tests/test_diff_coverage_action.py`: `action.yml` smoke test — valid
   YAML, `using: composite`, required `coverage-files` input, input defaults
   (origin/main / 80 / 10.3.0), setup-uv SHA-pinned, pinned diff-cover version threaded
   into the run body, inputs passed via `env:` (no `${{ inputs }}` in run body).

## Out of scope (explicitly deferred)
- **Stage 2** — WebUI consumes the action (separate repo, supervised Tier-3 delivery).
- **Stage 3** — monorepo self-consume (bigger: touches the HARD gate + `check_ci_gate_coverage`
  guard + wiring tests; the `measure_diff_coverage.py` copy there is the tested reference impl).
- python-monorepo adopt template (no vitest / no adoptee), WebUI `coverage.total`,
  WebUI hard-flip.

## Affected Boundaries
- `.github/actions/diff-coverage-gate/action.yml` (NEW io-boundary: GitHub Actions
  composite contract — inputs/defaults consumed by external callers).
- `shared/templates/github-actions/ci-supabase-nextjs.yml.template`,
  `ci-vite-hono.yml.template` (template → adoptee CI).

## Acceptance Criteria
- AC1: `action.yml` exists, is valid composite YAML, exposes the 4 inputs with the
  documented defaults, SHA-pins setup-uv, and runs the pinned `diff-cover` with
  `--compare-branch` + `--fail-under`.
- AC2: Both vitest templates' `diff-coverage` job invokes the action via `uses:` and
  no longer inlines `diff-cover@10.3.0`; warn-only + ubuntu-only + fetch-depth:0 preserved.
- AC3: `test_ci_template_diff_coverage.py` asserts the `uses:` reference (green).
- AC4: `test_diff_coverage_action.py` smoke test green.
- AC5: Existing convention/wiring tests stay green (no regression); full shared suite green.

## Confidence Calibration
- **Boundaries touched:** GitHub Actions composite-action contract (new); 2 vitest CI
  adopt templates.
- **Empirical probes run:**
  - action.yml + both templates parse as valid YAML; action is `using: composite` with
    the expected `[Install uv, Diff coverage]` steps. Finding: OK.
  - Shell-body probe (extracted `run:` body under `set -euo pipefail`, `git`/`uvx`
    shadowed): single-file, two-file, and non-default `origin/develop` inputs each
    produce byte-identical fetch-target + diff-cover argv vs the old inline templates;
    `read -r -a` does not trip `set -e` (exit 0). Behavior preserved + correctly
    generalized to `origin/<branch>`. Committed as `test_diff_coverage_action_runtime.py`.
  - Committed blob line-endings: `git ls-files --eol` → `i/lf` for action.yml (LF in the
    repo blob despite Windows CRLF working copy) → the Linux-runner bash body is `\r`-free.
  - Full affected suite green: 306 shared CI/coverage/template tests, 33 diff-cover tool
    tests, 18 adopt-scaffold tests, 43 action+convention tests; ruff clean.
  - External review (GPT-5.4) ship-with-fixes → all 3 findings addressed (origin/<branch>
    contract documented; coverage-files split via bash array; pin-threading assertion
    tightened to exact `diff-cover@${INPUT_DIFF_COVER_VERSION}` adjacency).
- **Test Completeness Ledger:** every behavior below is `tested` (cite) or `untestable`
  (closed-vocab reason_code); 0 testable-but-untested.

  | # | Behavior | Disposition | Evidence |
  |---|---|---|---|
  | 1 | 4 inputs w/ documented defaults (coverage-files req; compare-branch=origin/main; fail-under=80; diff-cover-version=10.3.0) | tested | `test_diff_coverage_action.py::TestDiffCoverageActionInputs` |
  | 2 | action is `using: composite` | tested | `test_diff_coverage_action.py` steps fixture |
  | 3 | setup-uv SHA-pinned | tested | `test_setup_uv_is_sha_pinned` |
  | 4 | pinned version threaded adjacent to `diff-cover@` (no `@latest` slip) | tested | `test_gate_threads_the_pinned_inputs` |
  | 5 | all 4 inputs consumed via `$INPUT_*`; `--compare-branch`+`--fail-under` passed | tested | `test_gate_threads_the_pinned_inputs` |
  | 6 | injection-safe (no `${{ inputs }}` in run body) | tested | `test_inputs_are_injection_safe` |
  | 7 | runtime: `origin/<branch>` fetch-target derivation (incl. non-default) | tested | `test_diff_coverage_action_runtime.py::test_wiring` |
  | 8 | runtime: space-separated coverage-files → distinct argv (1 & 2 files) | tested | same |
  | 9 | runtime: exact diff-cover argv assembly | tested | same |
  | 10 | nextjs template job → `uses:` action + coverage-files; warn-only; ubuntu; cobertura produced | tested | `test_ci_template_diff_coverage.py` |
  | 11 | vite-hono template same w/ two cobertura files | tested | same (parametrized over both vitest templates) |
  | 12 | no regression in convention/wiring/scaffold tests | tested | `test_ci_workflow_convention.py` + adopt scaffold + F0 full suite |
  | 13a | diff-cover exits non-zero when changed-line coverage < threshold (the gate DECISION) | untestable → `covered-by-existing-test` | proven against REAL diff-cover in `shared/scripts/tools/tests/test_measure_diff_coverage_gate.py` (same pinned binary); the action's argv wiring feeding it is rows 7-9, warn-only is rows 10-11 |
  | 13b | `git fetch --no-tags origin "$base"` makes `origin/<base>` resolvable on a `fetch-depth:0` checkout | not new behavior | verbatim the pre-existing template fetch line, identical to the monorepo `ci.yml` gate proven on real PRs (#328/#329/#330); a `fetch-depth:0` unit test can't run without a real Actions checkout, but this line is unchanged by the extraction |

- **Confidence-pattern check:**
  - *Asymptote (depth):* drove the action contract to exhaustion — static shape, all
    defaults, pinning, injection-safety, AND runtime argv across the input space that
    matters (single/multi/non-default-origin). Further probes stopped surfacing new
    failure modes.
  - *Coverage (breadth):* every enumerated behavior is `tested` or a cited
    `covered-by-existing-test`; none deferred.
  - *Integration composition:* no `cross_component` machinery touched — a CI composite
    action is not in `CROSS_COMPONENT_FILE_PATTERNS`, so the F11 verifier forces no
    integration-coverage row.
