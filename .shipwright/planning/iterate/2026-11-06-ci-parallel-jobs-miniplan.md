# Mini-Plan: ci-parallel-jobs

- **Run ID:** iterate-2026-11-06-ci-parallel-jobs

## Files to modify
- `.github/workflows/ci.yml` — edit (new jobs, gather job `python-checks`)
- `shared/tests/test_ci_coverage_wiring.py` — edit (steps now live in different jobs)
- `shared/tests/test_ci_parallel_jobs.py` — new (AC1-AC7 pinned on parsed YAML)
- `shared/scripts/tools/tests/test_f0_ci_parity.py` — edit if it reads steps from the single job
- other tests that fail after the split (found by running the suite; expected: main-health fixtures only name
  strings, which stay valid because `python-checks` keeps its name)
- `docs/hooks-and-pipeline.md` — edit (CI section: job topology + the fail-closed `needs` step)
- `scripts/verify_local.py` — only if its mirror list names moved steps

## Work breakdown
1. Read every test that parses `ci.yml` and list which assumptions break (job id, step names, step order across
   one job). Output: the list in this file's "Findings" (appended during build).
2. Write `test_ci_parallel_jobs.py` first (red): jobs exist, `needs`, `if: always()`, first-step `needs.*.result`
   check, no xdist, one root per pytest, upload `include-hidden-files`, scanner steps only in `tests-plugins`.
3. Edit `ci.yml`: add the four jobs (each: checkout fetch-depth 0, uv, python 3.11, `uv sync`, `plan`, run its
   roots with the SAME flags and junit/cov paths as today, upload artifact), then reduce `python-checks` to:
   result check, checkout, uv, python, `uv sync`, lint, download artifacts, `plan`, then the unchanged gate steps.
4. Update `test_ci_coverage_wiring.py` and any other red test; green the new test.
5. Update docs; run `verify_local.py` and the F0 suite.
6. Push; the PR's own CI run is the end-to-end probe (artifacts, combine, gates, fail-closed step).

## Test strategy
YAML-shape tests (parsed, never string matching), existing wiring/parity tests, the CI-gate guard, and the PR's
real run. No E2E surface.

## Alternative approach (rejected)
Move EVERYTHING (including gates) into per-root jobs plus a tiny fan-in. Rejected: it multiplies the places the
keystone/provenance/AC-ratchet step-shape tests and `ci_provenance`'s step lookup would need to follow, for no
wall-clock gain — the gates take < 1 min and must run after all coverage/JUnit exists anyway.
Second alternative: xdist inside the single job (~4 min saved). Rejected: a standing operator decision keeps CI
serial as the independent check against the parallel local F0 run; guarded by `test_ci_stays_SERIAL`.

## Revisions after the internal plan + architecture review (binding for the build)
- Gather job `python-checks` order: checkout, uv, Python, `uv sync`, `Lint (ruff)`, THEN the result step
  (`if: always()`, `toJSON(needs)` + jq, every result must be exactly `success`), then download + `plan` + the
  unchanged gates. Lint runs before the result step so a lint error is visible even when a test job failed.
- Artifacts: one per test job, named `ci-tests-<id>`, ONE multi-path upload of `.ci-junit/` + `.cov-data/`,
  `include-hidden-files: true`, `if-no-files-found: error`, `overwrite: true`, `retention-days: 2`, uploaded
  `if: always()`; download `pattern: ci-tests-*`, `merge-multiple: true`, `path: .`. `events-replay` has none.
- New fail-closed step `Coverage data set (gate)` between download and `Combine coverage`; registered in
  `verify_local.CI_ONLY_GATES`.
- Each coverage-producing job starts with `rm -rf .cov-data && mkdir -p .cov-data`; all jobs `fetch-depth: 0`.
- Scanner installs only in `tests-plugins`. Lint stays in `python-checks`.
- Extra files: `shipwright_run_config.json` (`required_checks_advisory`), `test_ci_reruns_the_full_verification_on_pr.py`
  (allow exactly `always()` on the gate job; extend gate-job list), `scripts/verify_local.py`, main-health fixtures.
- PR target is ~14-15 min (push ~10-11), not 10: the serial gate tail stays after the tests.

## Superseded by operator decision (2026-11-06): small variant
External review (GPT + GLM, both `reject` on the four-job shape) -> only `shared/tests` moves to `tests-shared`;
plugins, integration, the replay gate and all gates stay in `python-checks`. Everything above about
`tests-plugins` / `tests-integration` / `events-replay` jobs and their artifacts is dropped; the result step,
artifact conventions, `Coverage data set (gate)`, advisory declaration and test updates stay as listed.
Also from the external review: prove the result-step logic against synthetic `failure`/`cancelled`/`skipped`
results, and confirm on the PR run that a deliberately failing `tests-shared` turns `python-checks` red before merge.
