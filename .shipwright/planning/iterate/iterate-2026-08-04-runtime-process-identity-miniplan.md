# Mini-Plan: Retire obsolete runtime PID verifier

- **run_id:** `iterate-2026-08-04-runtime-process-identity`
- **complexity:** medium (`cross_component` floor from `verify_phase.py`)

## Files

- Delete `shared/scripts/tools/verifiers/runtime_checks.py`.
- Delete `shared/tests/test_verifiers_runtime.py`.
- Edit `shared/scripts/tools/verify_phase.py` to remove the import, selector,
  single-phase dispatch, and `all` dispatch entry.
- Edit `shared/scripts/tools/verifiers/__init__.py` and
  `shared/scripts/tools/verifiers/common.py` to remove stale package prose.
- Add `integration-tests/test_verify_phase_cli.py`.
- Edit `docs/hooks-and-pipeline.md` and `docs/guide.md` to remove the active
  runtime-verifier surface.

## Work Breakdown

1. Inventory the whole repository for active executable and documentation
   callers of `verify_phase.py --phase runtime`, plus imports/re-exports of
   `runtime_checks`; preserve immutable historical changelog records.
2. Add the CLI/dispatch integration regression and run it red against the
   current selector. Assert rejection/help, a surviving selector, and the exact
   ordered `all` registry.
3. Remove the obsolete module, dispatch, and stale package references; run the
   regression green.
4. Remove the dedicated legacy unit suite and update both documentation
   surfaces; scan again for active survivors.
5. Run the integration probe, `shared/tests`, canonical full suite, lint, and
   local merge guards; record run-specific evidence.

## Test Strategy

- One integration test process rooted only at `integration-tests` exercises the
  real verifier CLI boundary and the exact surviving dispatch order.
- One `shared/tests` process verifies remaining verifier/package behavior.
- The canonical full-suite runner remains the authoritative regression gate.
- Surface verification uses the same integration test as a CLI surface.

## Alternative Rejected

Treating the legacy producer's approximate `spawnedAt` wall-clock value as a
new process identity was rejected: the producer no longer exists, its value was
not an exact OS identity, and no real producer-to-file-to-consumer round trip
could be proven. Retargeting the change to Shipwright's dev-server state was
also rejected because it is a different runtime and outside P2.35.
