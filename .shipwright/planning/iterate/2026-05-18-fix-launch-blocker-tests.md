# Iterate Spec: fix-launch-blocker-tests

- **Run ID:** iterate-2026-05-18-fix-launch-blocker-tests
- **Type:** bug
- **Complexity:** medium
- **Status:** implemented

## Goal

Make every test suite green so the public-launch CI (activated in launch-prep
Step 4) is not red on the first PR. Reproduction surfaced **16 failures in 5
root-cause groups** — not the 13 the launch plan assumed — plus a broken CI
config (G6) and, once the fix ran in a fresh iterate worktree, a 17th failure
(G7) that a long-lived working copy had masked.

## Acceptance Criteria

- [ ] **AC-1 — bash hooks resolve a real Python.** `check_secrets.sh`,
  `check_file_size.sh` (shared) and `validate_command.sh`,
  `check_destructive_migration.sh` (build plugin) extract their JSON payload
  via a resolved interpreter that rejects the Windows Microsoft-Store
  `python3` stub. `shared/tests/test_hooks.py::TestCheckSecrets` (5),
  `::TestCheckFileSize::test_blocks_large_file`, and
  `plugins/shipwright-build/tests/test_hooks.py` (validate_command ×2 +
  destructive_migration ×1) all pass.
- [ ] **AC-2 — workflow tests reflect Go-Live.**
  `plugins/shipwright-security/tests/test_workflow_shape.py::TestDormantTriggers`
  asserts the post-launch active state (CI/CodeQL/Security triggers live, no
  DORMANT banner) instead of dormancy.
- [ ] **AC-3 — pytest summary parser is ANSI-robust.**
  `surface_verification.py::parse_tests_run` strips ANSI escape sequences
  before the `N passed` regex. `shared/tests/test_surface_verification.py`
  real-pytest tests (`test_real_pytest_round_trip_three_passing`,
  `test_real_pytest_failed_test_surfaces_exit_3`) pass.
- [ ] **AC-4 — canon detector ignores prose.**
  `test_artifact_path_canon.py::test_no_legacy_artifact_paths[compliance-migrated]`
  passes — a doc sentence mentioning `compliance/` no longer trips the
  legacy-path detector.
- [ ] **AC-5 — deploy missing-token warning names the variable.**
  `validate-deploy.py` emits a warning containing the literal
  `JELASTIC_TOKEN`; `test_validate_without_token` passes.
- [ ] **AC-6 — ci.yml can run the suites.** `.github/workflows/ci.yml`
  installs pytest before invoking plugin / integration tests (plugins
  declare pytest as an optional `dev` extra or not at all, so plain
  `uv sync && uv run pytest` cannot find it).
- [ ] **AC-7 — nested-shipwright fixture survives a fresh checkout.** The
  detector-marker fixture
  `plugins/shipwright-adopt/tests/fixtures/nested-shipwright/webui/shipwright_run_config.json`
  is tracked (re-included past the repo-wide `shipwright_*_config.json`
  ignore) so `test_nested_project_detector::test_detects_nested_shipwright_subproject`
  passes on a fresh clone / CI checkout / iterate worktree, not only in a
  long-lived working copy. (conventions.md line 72 — known, deferred.)
- [ ] **DoD** — all 13 plugin suites + `shared/tests/` + `integration-tests/`
  green.

## Spec Impact

- **Classification:** none
- **NONE justification:** This is a bug iterate. AC-1..AC-5 restore behavior
  the framework already intends (hooks detect secrets, the parser counts
  tests, the canon detector flags real legacy paths, deploy validation warns
  on missing config); AC-6 fixes CI config. No functional requirement
  changes — no user-visible capability is added, modified, or removed.

## Out of Scope

- Deduplicating the divergent `validate_command.sh` /
  `check_destructive_migration.sh` copies (shared vs build plugin) — the
  shared copies already parse without `python3`; only the build copies need
  the resolver. Dedup is a separate refactor.
- Changing what any hook *detects* — only how it resolves its interpreter.
- Removing the `--color=no` F0.5 runner convention (ADR-048) — it stays as
  defense-in-depth; AC-3 makes the parser robust regardless.

## Affected Boundaries

| Producer (writes) | Consumer (reads) | Format |
|---|---|---|
| Claude Code hook dispatch | `check_secrets.sh` / `check_file_size.sh` / `validate_command.sh` / `check_destructive_migration.sh` | JSON on stdin |
| pytest / playwright subprocess | `surface_verification.py::parse_tests_run` | ANSI-capable text |

Round-trip coverage: the existing `test_hooks.py` subprocess tests feed a
real JSON payload through each hook (producer→stdin→consumer); the
`test_surface_verification.py` real-pytest tests feed real subprocess output
through `parse_tests_run`. Both are genuine round-trips, not stubbed.

## Confidence Calibration

- **Boundaries touched:** JSON-on-stdin → 4 bash hooks (G1); ANSI-capable
  subprocess text → `parse_tests_run` (G3). See "Affected Boundaries" above.
- **Empirical probes run:**
  - Manual production-condition probe — ran `check_secrets.sh` with a real
    AWS-key JSON payload on this machine (where `python3` IS the Microsoft
    Store stub): exit 2 + "AWS Access Key ID detected" (was exit 0). Real
    producer→stdin→consumer round-trip.
  - `shared/tests/test_hooks.py` 32/32, `shipwright-build/tests/test_hooks.py`
    7/7 — subprocess round-trips through all 4 patched hooks.
  - F0.5 `surface_verification.py` cli runner — 66 tests parsed, exit 0:
    confirms G3, the ANSI-robust parser counts colour-wrapped pytest output.
  - Full suite swept twice (post-G6, post-G7): 1905 shared/integration +
    13 plugin suites = ~3902 tests, 0 failed.
- **Edge cases NOT probed + why acceptable:** hook behavior when *no* Python
  interpreter resolves at all — the resolver then fails open (exit 0),
  identical to the pre-fix behavior; every real machine has `python` or `py`,
  so this path is unreachable in practice. `surface=web`/`api` parsing — not
  touched by G3 beyond the shared ANSI strip, covered by existing tests.
- **Confidence-pattern check:** no "are you confident?"-style yes-then-bug
  pattern fired in this run; root causes were diagnosed empirically before
  any fix.

## Verification (medium+)

- **Surface:** cli
- **Runner command:** `uv run --with pytest --with pytest-mock pytest <failing-test subset> --color=no` then the full per-plugin + shared + integration sweep.
- **Evidence path:** `.shipwright/runs/iterate-2026-05-18-fix-launch-blocker-tests/`
