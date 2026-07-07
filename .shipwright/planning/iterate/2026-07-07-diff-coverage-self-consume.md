# Iterate spec — diff-coverage Stage 3: monorepo self-consume

- **Run ID:** `iterate-2026-07-07-diff-coverage-self-consume`
- **Intent:** CHANGE (Path B) — route the monorepo's own diff-coverage HARD gate through the shared composite action.
- **Complexity:** medium (touches the HARD merge gate #330 + the CI-gate guard + wiring tests).
- **Spec Impact:** NONE (behavior-preserving) — the gate still blocks PRs whose changed lines are <80% covered vs origin/main with pinned diff-cover@10.3.0; only the *definition site* moves from `measure_diff_coverage.py --fail-under` to the composite action. No FR (CI infra) → F5b No-FR branch (`change_type: infra`).
- **Stage 3 of the composite-action refactor** (Stage 1 #338, Stage 2 webui#210 delivered).

## Goal
The gate DECISION (threshold + pinned diff-cover + fail-under logic) lives in ONE place — the composite action — consumed by adopt templates (@main), WebUI (@main), and now the monorepo itself (local `./` path). Ends the last gate-logic duplication (`measure_diff_coverage.py::decide_gate` vs the action).

## Design (Design A — decided)
- `ci.yml` "Diff coverage (gate)" step → `uses: ./.github/actions/diff-coverage-gate` with `coverage-files: coverage.xml`. **Local `./` path** (not `@main`): a PR editing the action is gated by its OWN checkout (no bootstrapping wrinkle), and no mutable-tag Semgrep finding. NO `continue-on-error` (stays a HARD gate).
- `measure_diff_coverage.py` is NO LONGER the CI gate. It stays as: (a) the LOCAL dashboard producer (`.shipwright/coverage/diff_coverage.json`, read by `_diff_coverage_block.py` during compliance regen — never consumed in CI), (b) the tested reference impl (`test_measure_diff_coverage_gate.py` + the real-PR replay corpus). Untouched.
- **CI-gate guard** (`check_ci_gate_coverage.py`): add `diff-coverage-gate` to `GATE_USES` so the action `uses:` step is recognized as a gate — preserving the reverse-drift protection (a future `continue-on-error` on it → loose gate, no allowlist → guard FAILS). `diff-cover`/`measure_diff_coverage` stay in `GATE_COMMANDS` (defensive + unit-tested).
- **Artifact upload:** drop diff-cover.json/md (produced by measure_diff_coverage.py, now gone from CI); keep coverage.xml. The human-readable diff-cover report stays in the CI log (the action prints it).

## Verified pre-conditions (Repo Scout)
- The CI gate step is used PURELY as the gate — its dashboard-json side-effect is written-then-discarded (no CI consumer; `_diff_coverage_block.py` reads it only locally). ✓
- The action gate step matches none of the guard's gate signals (name has no keyword; `uses` not in GATE_USES) → guard would lose sight of it → MUST add to GATE_USES. ✓
- `python-checks` job checkout has `fetch-depth: 0` (the action's `git fetch origin main` needs it). [verify at build]

## Acceptance Criteria
- AC1: ci.yml "Diff coverage (gate)" step uses `./.github/actions/diff-coverage-gate` (local path) with `coverage-files: coverage.xml`, no continue-on-error, keeps `if: hashFiles('coverage.xml') != ''`, and still runs AFTER Combine.
- AC2: `measure_diff_coverage.py` no longer appears in ci.yml; the artifact upload no longer references diff-cover.json/md.
- AC3: guard classifies the action `uses:` step as a gate (`diff-coverage-gate` in GATE_USES); a continue-on-error on it → loose (unit test).
- AC4: `test_ci_coverage_wiring.py::test_diff_coverage_step_is_hard_gate` flipped to assert the `uses:` ref (not the inline wrapper); order test still green.
- AC5: `TestRealRepo::test_live_workflows_pass_the_guard` green against the refactored ci.yml (no loose gates, no stale allowlist); full shared suite green.

## Affected Boundaries
- `.github/workflows/ci.yml` (the HARD merge gate).
- `shared/scripts/tools/check_ci_gate_coverage.py` (`GATE_USES`) — the gate-classification guard.
- `shared/tests/test_ci_coverage_wiring.py`, `shared/tests/test_check_ci_gate_coverage.py` (drift-protection).

## Confidence Calibration
- **Boundaries touched:** the HARD merge gate (`.github/workflows/ci.yml`); the CI-gate
  guard (`check_ci_gate_coverage.GATE_USES`); two drift-protection tests.
- **Empirical probes run:**
  - Guard CLI against the refactored repo → `OK CI gate-coverage guard passed` (18 test
    dirs covered), exit 0. `TestRealRepo::test_live_workflows_pass_the_guard` +
    `test_live_allowlist_has_no_stale_entries` green against the live ci.yml.
  - ci.yml parses; `python-checks` checkout has `fetch-depth: 0` (the action's
    `git fetch origin main` needs it); gate step = `uses: ./.github/actions/diff-coverage-gate`,
    `with.coverage-files: coverage.xml`, continue-on-error absent, `if: hashFiles(...)`.
  - The action's gate itself was proven end-to-end in Stage 1 (extracted run body +
    real `diff-cover`: covered→exit 0, <80%→exit 1). This PR's OWN CI run is the live
    proof that the local `./` path resolves and gates (F0.5).
  - ruff clean; 53 wiring+guard tests green.
- **Test Completeness Ledger:**

  | # | Behavior | Disposition | Evidence |
  |---|---|---|---|
  | 1 | ci.yml gate uses `./…/diff-coverage-gate` + `coverage-files: coverage.xml`, no continue-on-error, `if: hashFiles`, no inline measure_diff_coverage.py | tested | `test_ci_coverage_wiring.py::test_diff_coverage_step_is_hard_gate` |
  | 2 | Combine still runs before the gate step | tested | `test_combine_runs_before_diff_after_all_tiers` |
  | 3 | guard classifies the action `uses:` step as a gate | tested | `test_check_ci_gate_coverage.py::…_action_uses_is_gate` |
  | 4 | continue-on-error on the action gate → loose (reverse-drift caught) | tested | `…_action_continue_on_error_is_loose` |
  | 5 | the refactored LIVE ci.yml passes the guard (no loose gates, no stale allowlist) | tested | `TestRealRepo::test_live_workflows_pass_the_guard` + `…_no_stale_entries` |
  | 6 | the action's real `diff-cover@10.3.0 --fail-under=80` gate BITES (the decision the monorepo hard gate now rests on) | tested | `test_diff_coverage_action_gate_bites.py` — executes the extracted action `run:` body with REAL diff-cover: covered(100%)→exit 0, under-covered(50%)→exit non-zero |
  | 7 | the local `./` action path resolves on the fetch-depth:0 checkout | untestable → `covered-by-existing-test` | local-path resolution is a GitHub-Actions mechanism, exercised by THIS PR's own python-checks CI run (F0.5); the gate logic itself is row 6 |
  | — | artifact upload drops diff-cover.json/md | not a testable behavior | `if-no-files-found: ignore` made keeping vs dropping missing paths behaviorally identical — pure cleanup, no observable change |

  0 testable-but-untested; the single `untestable` row cites a valid closed-vocab reason. (F1 fix: the replay-corpus MANIFEST refresh note updated — diff-cover.json is no longer a CI artifact.)
- **Confidence-pattern check:**
  - *Asymptote (depth):* drove the guard interaction to exhaustion — classification (gate),
    reverse-drift (loose), forward-drift (stale allowlist), and the live-repo run.
  - *Coverage (breadth):* every enumerated behavior tested or a cited covered-by-existing-test.
  - *Integration composition:* the `cross_component` risk flag covers hooks/phase-validators/
    churn machinery — NOT CI-gate config; a CI workflow + its guard are not in
    `CROSS_COMPONENT_FILE_PATTERNS`, so no integration-coverage row is forced. (The
    guard×ci.yml interaction IS the composition here, and `TestRealRepo` proves it.)
