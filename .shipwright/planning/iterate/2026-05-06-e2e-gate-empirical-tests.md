# Iterate Spec: F0.5 Empirical-Test Backfill

- **Run ID:** iterate-2026-05-06-e2e-gate-empirical-tests
- **Type:** change (extending test coverage on the just-merged F0.5 gate)
- **Complexity:** small (test-only changes; no production code)
- **Status:** in_progress
- **Follows:** iterate-2026-05-06-e2e-verification-gate (ADR-037, merge 35b66aa)

## Goal

Close the empirical-test gap from plan §Verification on
`ich-m-chte-am-iterate-polished-puffin.md`. The previous iterate landed
the F0.5 gate with strong unit-test coverage but skipped several real
end-to-end probes.

## Acceptance Criteria

- [ ] AC-1: Drift-protection test asserts Phase Matrix, F0.5 section,
      and design-and-testing.md keep "always at medium+" semantics in
      sync. Failing one of the three keywords fails the test loudly.
- [ ] AC-2: `parse_tests_run` is exercised against **real** pytest
      stdout (run a tiny fixture suite, pipe its stdout through the
      parser, assert non-zero count). No `--tests-run` override —
      the parser is on the critical path.
- [ ] AC-3: Greedy-filter trap reproduced with a **real** `pytest -k
      "non_matching_pattern"` invocation through `verify_surface`.
      Asserts `EXIT_ZERO_TESTS` (= 2). No override.
- [ ] AC-4: End-to-end audit chain via the `verify_iterate_finalization.py`
      CLI (not just the check function). Seed a fake project state for
      each fail-closed condition; assert exit codes line up.
- [ ] AC-5: Backend-affects-Frontend rule is documented in
      conventions.md (already done in previous iterate's Unit E) and
      cross-checked by a presence test so future edits don't drop it.
- [ ] AC-6: Retry-cap probe runs against a real subprocess that takes
      time + always exits non-zero, so we measure cumulative attempts
      rather than rely on the single-call `sys.exit(1)` unit test.

## Affected FRs

n/a — meta-iterate on the iterate skill's own tests.

## Out of Scope

- Real Playwright run on a webui fixture (deferred — `.shipwright-webui/`
  is just a workspace file; no Playwright project exists).
- Real medium+ iterate end-to-end against `dev_server.py` lifecycle
  (would need a fixture project; cost/benefit-negative inside the
  framework repo itself).

## Affected Boundaries

n/a — test-only iterate. No new producer/consumer pair.

## Confidence Calibration

- **Boundaries touched:** none (no new schema or producer/consumer pair)
- **Empirical probes run:** the iterate IS the empirical probe layer
- **Edge cases NOT probed + why acceptable:** webui Playwright smoke
  deferred (no fixture available)
- **Confidence-pattern check:** previous iterate's "are you confident"
  surfaced this gap → this iterate IS the response (asymptote heuristic
  fired)

## Verification (small, no F0.5 mandatory)

- **Surface:** cli (the iterate is itself test backfill)
- **Runner command:** `uv run pytest plugins/shipwright-iterate/tests/ shared/tests/ -q`
- **Evidence path:** stdout
