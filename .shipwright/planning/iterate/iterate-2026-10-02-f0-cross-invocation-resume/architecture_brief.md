# Architecture Brief: f0-cross-invocation-resume

## The problem

When a unit of the pre-push test gate (F0) goes red, the developer fixes it and re-runs the
gate. Today that re-run executes every test of every unit again; for the largest unit that is
15-22 minutes per fix round, although typically one or two tests were red and everything else
already passed minutes ago. The merge pipeline's full CI run happens anyway on every PR.

## What already exists here

- The gate runner (`run_test_suite.py`) runs ~18 units in parallel and, inside ONE invocation,
  already retries a red unit on its red tests only, using pytest's own failed-test cache.
- Each invocation retains every unit's JUnit report and coverage data for evidence and for the
  diff-coverage gate; a reset wipes coverage state at the start of every invocation.
- CI re-runs the full suite serially on every pull request and is the authoritative gate.

## What would newly, permanently exist

A small on-disk record, written at the end of a run that had a red unit and deleted by the
first fully green run, that lets the NEXT gate invocation skip tests that were already green
and re-run only the red ones. It lives in the main repository's gitignored runs directory,
per checkout; the gate runner itself keeps it correct (it refuses the record whenever it
cannot prove it still describes the unit). The resulting evidence is labelled as resumed.

## Options on the table

- **A:** Persist per-unit results between invocations and resume from them, even when the fix
  changed non-test source files.
- **B:** Persist per-unit results but resume only when no non-test file changed.
- **C:** Keep today's behaviour (re-run everything), optionally only speeding up the retry
  inside one invocation.
- **D:** Select tests to run from the diff instead of from prior results.

## Constraints that are not negotiable

- The merge gate in CI stays a full serial run of everything (it is the safety net).
- A resumed result must never be presented or staged as a full green run.
