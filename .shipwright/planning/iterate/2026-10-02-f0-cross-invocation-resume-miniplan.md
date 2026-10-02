# Mini-Plan: f0-cross-invocation-resume

- **Run ID:** iterate-2026-10-02-f0-cross-invocation-resume
- **Spec:** `.shipwright/planning/iterate/2026-10-02-f0-cross-invocation-resume.md`
- **Scope:** operator option A (resume allowed after a source edit; CI is the net).

## Files
New (each < 300 lines): `shared/scripts/tools/suite_resume_state.py` (tree snapshot, atomic
state), `suite_resume.py` (planning, narrow execution, persistence), `suite_resume_cov.py`
(coverage restore/purge), `suite_resume_report.py` (console block, manifest marking, gate rule).
Edit: `run_test_suite.py` (`prepare_resume` after the coverage reset, `try_resume` in the unit
pool, `persist` before publish, fallback loop in `_run_locked`; net <= 529 lines),
`suite_retry.py` (record the verdict attempt's cache dir), `suite_retention.py` (`extra`,
`pending_report`), `stage_f0_evidence.py` + `evidence_drop.py` (`resumed_local` provenance),
`check_ac_ratchet_f0.py` (notice), `F0.md`, `docs/hooks-and-pipeline.md`,
`test_f0_cli_diff_coverage_e2e.py` (module list of the synthetic repo).
Tests: `test_suite_resume_state.py`, `test_suite_resume.py`, `test_suite_resume_exec.py`,
`test_suite_resume_report.py`, `test_stage_f0_evidence_resumed.py`,
`test_f0_resume_real_pytest.py`, fixtures in `_resume_fixtures.py`.

## Work breakdown
1. `suite_resume_state` + tests (snapshot over all files, atomic save/load, refusals).
2. `suite_resume_cov` + tests (purge by per-file hash; unknown = stale).
3. `suite_resume` planning + execution + persistence with a fake `_exec`.
4. Wire into `run_suite` / `_run_locked`; keep every existing F0 test green unchanged.
5. Evidence marking (`Retention.extra`, staging provenance), console block, docs.
6. Real-pytest + real-git fix-round integration test (AC-10).

## Test strategy
Fake `_exec` unit tests for every refusal branch; real `uv run pytest` + `git` for the fix
round; hard-fail in CI when uv/git are missing (skip locally with a hint only).

## Alternative approach (rejected)
Gate the resume on an unchanged tree hash (the deferral's condition (i)): sound but useless -
a fix always changes the tree, so it would never resume. Rejected by the operator decision.
Second: keep the whole-suite re-run only (status quo): costs 15-22 min per fix round.

## Risks
- A regression inside a reused result is invisible locally (accepted by operator; CI catches).
- Coverage of an edited file is rebuilt from the red tests only, so the gate can refuse a
  resume that a full run would pass: handled by the one-shot full re-run fallback.
