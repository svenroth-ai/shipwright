# Mini-Plan: f0-failed-only-retry

- **Run ID:** iterate-2026-10-02-failed-only-retry
- **Spec:** `.shipwright/planning/iterate/2026-10-02-f0-failed-only-retry.md`
- **Scope:** in-run failed-only retry only. Cross-invocation resume deferred (spec "Decision").

## Files
New (each < 300 lines):
- `shared/scripts/tools/suite_failed_only.py` - `read_lastfailed`, `junit_failure_count`, `failed_only_ok`, `merge_junit`, `FAILED_ONLY_ARGS` (written).
- `shared/scripts/tools/suite_retry.py` - the retry loop extracted from `run_suite`, plus the failed-only branch; seams injected through an `ops` namespace.
Edit:
- `shared/scripts/tools/run_test_suite.py` - `build_command(..., cache_dir=None, extra_args=())`; `_exec(..., cache_dir=None, extra_args=())` defaults the cache to `<tmp_dir>/c`; `run_suite` delegates the loop; net lines <= 529.
- `shared/scripts/tools/suite_report.py` - `failed-only` marker in the retry block (ASCII).
- `plugins/shipwright-iterate/skills/iterate/references/F0.md`, `docs/hooks-and-pipeline.md` - document behaviour.
Tests (new files, each < 300 lines): `test_suite_failed_only.py`, `test_suite_retry.py` (fake `_exec`), `shared/scripts/tools/tests/test_f0_failed_only_real_pytest.py`.

## Work breakdown
1. `suite_failed_only` + unit tests (cross-check, merge incl. key collision / collection-error / unparsable).
2. `build_command`/`_exec`: cache dir + extra args; default argv unchanged (existing tests pin it).
3. Pure-refactor step: move the retry loop to `suite_retry.retry_red_units` with injected seams; run every existing F0 test file unchanged -> green BEFORE adding behaviour.
4. Add the failed-only branch (AC-1..5): failed_only_ok -> failed-only argv on the SAME cache dir; rc 5 / merge failure -> whole-unit path; coverage cleared only on whole-unit path.
5. Report marker; docs.
6. Real-pytest integration test (AC-7); one root per pytest process.

## Test strategy
Unit tests with tmp files + fake `_exec` (existing style in `test_run_test_suite_faults.py`). Integration: real `uv run pytest` subprocesses on a temp project via the runner's own `_exec`/`build_command` (xdist first attempt, `--lf` retry), incl. teardown-error + collection-error fallbacks and coverage append. Hard-fail in CI if uv is missing; skip locally with a hint only when `uv` is not on PATH.

## Alternative approach (rejected)
JUnit-derived node ids instead of pytest's `lastfailed`: classname -> path mapping is lossy (nested classes, parametrize ids, per-unit rootdir). Second: cross-invocation resume now (operator option A bound) - cut by three reviews, see spec.

## Risks
- Union coverage includes lines a red attempt ran before failing (disclosed).
- Teardown-error tests: JUnit may emit one testcase with two children; counted once, cross-check holds or falls back safely.
