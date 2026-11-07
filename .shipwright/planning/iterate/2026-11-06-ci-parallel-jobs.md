# Iterate Spec: ci-parallel-jobs

- **Run ID:** iterate-2026-11-06-ci-parallel-jobs
- **Type:** change
- **Complexity:** medium
- **Status:** draft

## Goal
`ci.yml` runs one serial job (`Python (lint + test)`, ~16 min on push, ~20 min on a PR). Run the 8-minute
`shared/` test tier and the plugins + integration + replay tier as two parallel jobs that stay internally serial,
and keep `Python (lint + test)` as the one required check that lints, gathers both tiers' results by artifact and
runs every gate step. Target ~12 min push (max of the two parallel tiers + one setup + the gates). CI-duration iterate 2/3 (1/3 = PR #1000 Windows paths filter; 3/3 =
shard `shared/tests`).

**Shape decision (operator, 2026-11-06).** The first plan split all four tiers into four jobs. Both external
reviewers (GPT, GLM) rejected that as disproportionate (+~1 min saved for three more jobs/artifacts to maintain);
the internal architecture reviewer was for four jobs to prepare 3/3. The operator chose the small variant: only
`shared/tests` moves; 3/3 decides on evidence whether more jobs pay off.

**Correction after code + doubt review (same day).** "Only `tests-shared` moves, plugins/integration/replay stay in
`python-checks`" cannot be parallel: `python-checks` has `needs: [tests-shared]`, and a job with `needs` starts only
after they finish, so it would run the other tiers AFTER the shared tier (slower than before, one extra setup).
The smallest shape that is really parallel is TWO test jobs without `needs` (`tests-shared`, `tests-main` =
plugins + integration + replay + the scanner installs they need) and `python-checks` as the thin gather job
(lint, collect, gates). This is still far from the rejected four-job split: three jobs, one extra artifact,
all gate steps and their names untouched.

## Acceptance Criteria
- [ ] AC1 — `ci.yml` declares `tests-shared` (name `Tests (shared)`) and `python-checks` (name
  `Python (lint + test)`); `python-checks` lists `tests-shared` and `tests-main` (name `Tests (plugins + integration + replay)`) in `needs`;
  the two test jobs have no `needs` themselves. A job that runs pytest or `events_replay_gate` and is not one of
  the test jobs, or is missing from `python-checks.needs`, fails a test (reverse drift); a job with `needs` runs
  no test step.
- [ ] AC2 — `python-checks` has job-level `if: always()` (never `!cancelled()`); a step with its own `if: always()`
  reads `toJSON(needs)` and fails unless EVERY needed job's result is exactly `success` (failure, cancelled and
  skipped each fail), with the logic proven against synthetic results. No needed job carries a job-level
  `continue-on-error`. (FR-01.17/AC02: silence is not a pass.)
- [ ] AC3 — no job uses xdist (`-n`, `--numprocesses`, `pytest-xdist`) and every `pytest` invocation names exactly one
  test root (ADR-044); `test_ci_stays_SERIAL` stays green.
- [ ] AC4 — each test job (`tests-shared`, `tests-main`) uploads `.ci-junit/` and `.cov-data/` together as ONE multi-path artifact (`ci-tests-shared`, `ci-tests-main`)
  with `include-hidden-files: true`, `if-no-files-found: error`, `overwrite: true`, short `retention-days`, `if:
  always()`; `python-checks` downloads `pattern: ci-tests-*` with `merge-multiple: true`, `path: .`, after the result step and BEFORE Combine and BEFORE `Combine coverage`; `ci_junit_plan.py verify` still passes only when
  every planned root's report is present.
- [ ] AC5 — a fail-closed `Coverage data set (gate)` step (tool `check_ci_coverage_data_set.py`, registered in
  `verify_local.CI_ONLY_GATES`) sits between the download and `Combine coverage` and fails when `.coverage.shared`,
  `.coverage.integration` or any `.coverage.<plugin>` (plugins with pyproject + tests + scripts) is missing or empty.
- [ ] AC6 — every gate step of `python-checks` that existed before keeps its name, `if:` and relative order.
- [ ] AC7 — the scanner installs (Semgrep, Trivy, Gitleaks) run exactly once, in `tests-main` (the security plugin's
  smoke tests need them), and `Lint (ruff)` stays in `python-checks` exactly once;
  `tests-shared` runs `rm -rf .cov-data && mkdir -p .cov-data` before its first `COVERAGE_FILE=`; all three jobs use
  `fetch-depth: 0` and the same pinned setup sequence (checkout, uv, Python 3.11, `uv sync`).
- [ ] AC8 — required checks unchanged (`Python (lint + test)` only); the new checks `Tests (shared)` and `Tests (plugins + integration + replay)` are declared in
  `shipwright_run_config.json` `required_checks_advisory` so the required-checks-drift producer files no card.
- [ ] AC9 — `test_ci_reruns_the_full_verification_on_pr.py` (FR-01.17/AC01) permits exactly `always()` on
  `python-checks` and treats `tests-shared` and `tests-main` as gate jobs too; the coverage wiring test, a main-health fixture with
  the new job prefix, `verify_local.py` and `docs/hooks-and-pipeline.md` describe the new structure and are green.

## Spec Impact
- **Classification:** none
- **NONE justification:** CI job topology only. FR-01.17/AC01 (the gate job is unconditional on a PR) and AC02 (silence is not a pass) and FR-01.19
  (every merged commit is verified on its own, concurrency group untouched) keep their promises; `always()` only
  strengthens the first. The proving test of AC01 changes shape (AC9), the requirement text does not.

## Out of Scope
- Sharding `shared/tests` (iterate 3/3), xdist, caching git fixtures, changing the Windows workflow.

## Design Notes
- Smaller blast radius than "move everything": the gate steps stay in `python-checks` with identical names, so the
  ~12 tests that pin keystone/provenance/AC-ratchet/manifest step shapes keep working. Only the test-running steps
  move; their pinning tests (`test_ci_coverage_wiring.py`, `test_main_health_tool.py` fixtures, parity tests) are
  updated.
- `plan.json` is deterministic and its junit paths are absolute under the workspace, which is identical on every
  runner, so each test job and the gather job regenerate it instead of passing it around.
- `tests-shared` keeps the three `shared/` roots in ONE job so they keep sharing `.cov-data/.coverage.shared`
  (`--cov-append`); splitting them is iterate 3/3.
- Failure semantics: a failing test job leaves `python-checks` to run (`always()`), where the first step turns
  `needs.*.result` into a red required check. Without it GitHub treats a skipped required check as passing.

## Affected Boundaries
| Producer (writes) | Consumer (reads) | Format |
|---|---|---|
| test jobs: `.ci-junit/*.xml`, `.cov-data/.coverage.*` | `python-checks`: `ci_junit_plan.py verify`, `combine_coverage.py`, `ci_manifest_drift_check.py` | JUnit XML, coverage SQLite |

## Confidence Calibration
- **Boundaries touched:** artifact hand-off between jobs (hidden dirs, absolute junit paths, coverage `relative_files`).
- **Empirical probes run:** the PR's own CI is the probe — verify (a) all planned roots arrive, (b) `combine_coverage`
  yields a coverage.xml with plugin + shared + integration paths, (c) a deliberately failing needed job turns
  `python-checks` red (covered by the YAML-shape test + inspected on the PR run).
- **Test Completeness Ledger:** see F5 block.
- **Confidence-pattern check:** the real gap is anything only observable on GitHub (artifact upload of hidden files,
  `needs` result semantics); those rows are `untestable` with `requires-external-nondeterministic-service` and are
  proven by the PR's own run before merge.

## Verification (medium+)
- **Surface:** none
- **Justification (only if surface=none):** CI workflow topology; no startable surface. Structure is pinned by YAML
  tests; behavior is proven by the PR's own CI run.

## Architecture Review
- **Brief:** `.shipwright/planning/iterate/iterate-2026-11-06-ci-parallel-jobs/architecture_brief.md`
- **Verdicts:** glm=revise (smaller shape) · openai=reject (four jobs not justified yet); internal Opus reviewer: build as specified
- **Smallest thing that would do (per reviewers):** `python-checks` unchanged + one `tests-shared` job
- **Findings:** (1) four jobs disproportionate for ~1 min — accepted, shape reduced to `tests-shared` only;
  (2) prove the fail-closed `needs` step against synthetic failure/cancelled/skipped results — accepted (test);
  (3) cancelled-run behaviour of `always()` should be documented — accepted (docs/hooks-and-pipeline.md);
  (4) add a deliberately failing `tests-shared` probe before merge — accepted (done on the PR run);
  (5) root lists must stay disjoint across jobs — accepted (reverse-drift shape test).
- **Reconciliation:** the plan had four jobs to prepare iterate 3/3; the operator chose the small variant on
  2026-11-06. 3/3 decides on measured evidence whether to fan out further.
