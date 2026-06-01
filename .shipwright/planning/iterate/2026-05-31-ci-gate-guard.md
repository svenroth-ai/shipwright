# Iterate Spec — CI Gate-Coverage Guard

- **run_id:** `iterate-2026-05-31-ci-gate-guard`
- **Intent:** FEATURE (new guard) + CHANGE (harden existing CI gates)
- **Complexity:** medium (locked)
- **Risk flags:** `touches_io_boundary` (the guard parses `.github/workflows/*.yml` via `yaml.safe_load`)
- **Mode:** `--autonomous` (no interview; the invocation description is the locked scope)
- **Spec Impact:** ADD (new guard module + tests) · MODIFY (`ci.yml`, `security.yml`)

## Why this exists

`ci.yml` was authored "dormant" (commit 4107a6b, early-access) with `|| true` +
`continue-on-error` baked in, then only PARTIALLY hardened (2671c69 / d85210f added
scanners + CI-aware tests + a CodeQL guard) — leaving **lint, integration, shared
test coverage, and type gates loose**. Nothing prevents this regressing. We need a
meta-guard that runs in CI and fails when a quality gate goes silently loose or a
new test directory is silently uncovered.

## Empirical baseline (probes run during scout — see Confidence Calibration)

| Surface | State (measured) | Consequence |
|---|---|---|
| `shared/tests` | 2635 pass / 14 skip — GREEN | safe to gate |
| `shared/scripts/tests` + `shared/scripts/tools/tests` | 224 pass / **2 fail** | 2 non-hermetic `test_validate_env.py` tests (host-env pollution); must fix to gate |
| `integration-tests/` | 136 pass — GREEN | safe to remove `\|\| true` |
| `ruff check .` | **261 violations** (175 autofixable); ruff not even a declared dep | lint cleanup is its own iterate — cannot gate now |
| live `plugins/*/tests` coverage | loop `for plugin in plugins/*/` (gating) | covered |
| live `shared/**/tests` coverage | **none** | the "silently uncovered" gap |

## Acceptance Criteria

- **AC1** — Guard Check (a): every test dir under `plugins/*/tests`, `shared/**/tests`,
  `integration-tests/` is referenced by a CI pytest invocation; fails (non-zero) on an
  uncovered dir. *(unit test: inject an uncovered fixture dir → guard reports it)*
- **AC2** — Guard Check (b): every quality-gate step (test/lint/type/scan/analyze) that
  carries `|| true` or `continue-on-error: true` must appear in a documented allowlist;
  fails on a non-allowlisted loose gate. *(unit test: inject `|| true` on a non-allowlisted
  step → guard reports it)*
- **AC3** — Allowlist is an SSoT with **both-direction** drift protection: forward (every
  allowlist entry resolves to a real loose step in a real workflow — no stale entries) +
  reverse (Check b itself).
- **AC4** — Guard Check (c): the `security.yml` critical-gate must fail-closed on a missing
  / unparseable `findings.json` (no silent `2>/dev/null || echo 0` → green). Both the
  workflow is fixed AND the guard prevents regression.
- **AC5** — CodeQL `analyze` `continue-on-error` is tracked as a launch-gate
  (`launch_gate: true`) that MUST be removed at public launch; guard exposes the launch-gate
  registry and a test pins it.
- **AC6** — The guard runs as a **gating** step in `ci.yml` and PASSES against the live repo
  (achieved by: hardening integration, adding shared-test coverage, allowlisting the
  by-design/tracked-debt loose gates).

## Design

### New module: `shared/scripts/tools/check_ci_gate_coverage.py`
Pure functions (testable) + a CLI (`--project-root`, exit non-zero on any violation):
- `discover_test_dirs(root)` → posix-relative dirs matching `plugins/*/tests`,
  `shared/**/tests`, `integration-tests` (only if it holds `test_*.py`).
- `parse_workflows(root)` → list of `(file, job, step_name, run_body, continue_on_error, uses)`.
- `check_test_dir_coverage(dirs, steps)` → uncovered dirs.
  - `plugins/<seg>/tests` covered by a `plugins/*` glob in a pytest-bearing run body (loop).
  - other dirs covered by a literal posix reference in a pytest-bearing run body.
- `check_loose_gates(steps, allowlist)` → non-allowlisted loose gate steps.
  - gate step = run body invokes `pytest|ruff|mypy|pyright|tsc|eslint|flake8|semgrep|trivy|gitleaks`
    OR `uses:` a `codeql-action/(analyze|upload-sarif)` OR scan/sarif keyword.
  - loose = `continue-on-error: true` OR run body matches `\|\|\s*(true|:)` on the gate command.
- `check_allowlist_not_stale(steps, allowlist)` → entries with no matching real loose step.
- `check_security_findings_gate(steps)` → the critical-gate step must contain a
  missing-file guard and must NOT default the critical count to 0 on a missing file.
- `LOOSE_GATE_ALLOWLIST` — inline SSoT. Entry: `{workflow, step, reason, category, launch_gate}`.
  - `category="by-design"`: security scan (×3) + upload-sarif, codeql analyze.
  - `category="tracked-debt"`: ci.yml ruff lint (261-violation cleanup deferred to a
    follow-up iterate; documented, NOT silent).
  - `launch_gate=true`: codeql analyze (+ security upload-sarif) — revisit at public launch.

### Workflow changes
- `ci.yml`: remove `|| true` from the integration-tests step (now gating); add a gating
  **Run shared tests** step (`shared/tests`, `shared/scripts/tests`, `shared/scripts/tools/tests`);
  add a gating **Run CI-gate guard** step. Lint step stays loose but is now allowlisted as
  tracked-debt (its `|| true`+continue-on-error remain, documented).
- `security.yml`: the critical-gate step gains an explicit missing/invalid-`findings.json`
  fail-closed branch.
- `shared/scripts/tests/conftest.py` (new): autouse fixture clears profile env vars so the dir is hermetic (kept out of `test_validate_env.py` to avoid ratcheting its 883-LOC bloat baseline).

### Deliberate scope boundary (deviation, documented)
The invocation's literal allowlist names only "codeql analyze + security SARIF/scan steps".
**ruff lint** is added as a `tracked-debt` allowlist entry rather than hardened, because
making it gate requires resolving 261 pre-existing violations — a separate cleanup iterate.
This keeps the loose gate **explicit and visible** (the core ask: no *silent* loose gates)
instead of pretending lint is clean. Tracked for follow-up.

## Affected Boundaries
- **`.github/workflows/*.yml`** (consumer): the guard reads them via `yaml.safe_load` +
  text-scans `run:` bodies. Round-trip/boundary probe required (`touches_io_boundary`).
- **CI gating contract**: integration tests + shared tests move from non-gating → gating.
- **`shipwright_test_results.json`**: F5 records `test_completeness`.

## Confidence Calibration
- **Boundaries touched:** `.github/workflows/{ci,security}.yml`; `yaml.safe_load` parse of
  workflow YAML (`lib/ci_gate_scan.py`); `shared/scripts/tests` hermeticity; CI gating contract.
- **Empirical probes run:**
  - `ruff check .` → 261 violations, ruff not a declared dep ⇒ lint gate is a phantom; allowlisted as tracked-debt (not hardened).
  - `shared/tests` → 2635 pass; `shared/scripts/tests`+`tools/tests` → 224 pass + **2 fail** (host-env pollution); `integration-tests` → 136 pass.
  - Root-caused the 2 failures: `validate()` does `available_vars.update(os.environ)` (env overrides file) + host exports `NEXT_PUBLIC_SUPABASE_*` ⇒ non-hermetic test, not a product bug. Fixed via autouse delenv → 59 pass.
  - Combined `pytest shared/tests shared/scripts/tests …` → collection error (duplicate basenames) ⇒ CI must loop per-dir (mirrors plugin loop). Each dir green run separately.
  - Ran the guard against the **un-hardened** repo → correctly reported all 4 violation classes (red); against the **hardened** repo → `OK`, 17 dirs, exit 0 (green). Discriminates.
  - Independent adversarial review found 1 MAJOR (M1: decoupled security-gate detection) + 5 minor evasion/false-positive gaps; all fixed + pinned by regression tests.

- **Test Completeness Ledger** (testable ⇒ tested; 0 untested-testable):

  | Behavior | Disposition | Evidence |
  |---|---|---|
  | (a) uncovered test dir flagged | tested | `test_uncovered_dir_is_flagged`, `test_plugin_dir_uncovered_without_loop` |
  | (a) plugins-loop / literal coverage recognized | tested | `test_plugins_loop_covers_plugin_dirs`, `test_literal_referenced_dir_is_covered` |
  | (a) non-pytest body ≠ coverage | tested | `test_non_pytest_step_does_not_count_as_reference` |
  | (a) plugin w/o pyproject not discovered | tested | `test_plugin_tests_without_pyproject_not_discovered` |
  | (a) fixtures/vendored dirs excluded | tested | `test_discovers_roots_and_excludes_fixtures` |
  | (b) loose gate (`|| true` / `continue-on-error` / `|| exit 0`) flagged | tested | `test_injected_pipe_true…`, `…continue_on_error…`, `test_pipe_exit_zero_on_gate_is_loose` |
  | (b) allowlisted loose gate tolerated | tested | `test_allowlisted_loose_gate_is_not_flagged` |
  | (b) clean gate / loose non-gate not flagged | tested | `test_clean_gate_is_not_flagged`, `test_loose_nongate_step_is_not_flagged` |
  | (b) install/artifact steps not gates | tested | `test_install_step_is_not_gate`, `test_artifact_upload_is_not_gate` |
  | (b) comment/echo lines don't false-trip | tested | `test_comment_line_quoting_loose_form_not_loose`, `test_pipe_true_on_nongate_line…` |
  | (c) silent `|| echo 0` / `2>/dev/null` default flagged | tested | `test_silent_default_gate_is_flagged` |
  | (c) warning-only missing branch flagged (M1) | tested | `test_warning_only_missing_branch_is_flagged` |
  | (c) fail-closed (`[ ! -f ]`/`! test -f` + exit) accepted | tested | `test_fail_closed_gate_is_ok`, `test_test_dash_f_form_is_ok` |
  | (c) absent gate step flagged | tested | `test_absent_gate_step_is_flagged` |
  | AC3 allowlist forward drift (stale / hardened-but-listed) | tested | `test_entry_with_no_matching_step_is_stale`, `test_entry_matching_hardened_step_is_stale` |
  | AC5 codeql tracked as launch gate; each launch gate has reason | tested | `test_codeql_analyze_tracked_as_launch_gate`, `test_every_launch_gate_has_a_reason` |
  | boundary: workflow YAML round-trip; malformed YAML skipped | tested | `test_parse_captures_continue_on_error_and_run`, `test_malformed_yaml_is_skipped_not_crash` |
  | AC6 live workflows pass the guard | tested | `test_live_workflows_pass_the_guard`, `test_live_allowlist_has_no_stale_entries`, guard CLI exit 0 |
  | `validate_env` file-based tests hermetic | tested | 59 pass with host env vars set (autouse delenv) |
  | ci.yml/security.yml **runtime** execution on the GH Actions runner | untestable (`covered-by-existing-test`) | the guard's `run_all(REPO_ROOT)` statically asserts the live workflow shape; actual runner execution is CI itself |

- **Confidence-pattern check:**
  - *Asymptote (depth):* guard exercised in both red and green states against the real repo; adversarial review drove evasion-class fixes (M1 + m1–m5) each with a regression test — further probing now surfaces only fixed edge cases.
  - *Coverage (breadth):* 40 unit tests over all 6 ACs + boundary + live-repo; all 5 touched source/test files ≤300 LOC; full `shared/tests` + `shared/scripts/tests` + `tools/tests` + `integration-tests` green.
