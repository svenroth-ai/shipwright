# Architecture Brief: f0-failed-only-retry

## The problem

When a test fails in the pre-push full-suite gate (F0), the gate re-runs the whole red
test unit - up to ~22 minutes for the largest one - even though usually one or two tests
are red. Measured over 146 red unit runs: about two thirds pass when re-run alone with no
code change (a race), one third are real failures that the developer then fixes before
re-invoking the gate, which starts again from zero. F0 is ~77 % of an iterate's wall clock.

## What already exists here

- The F0 runner runs every test unit in parallel, retries a red unit once, serially and whole.
- A failed attempt's coverage is cleared before the whole-unit retry.
- A coverage-based diff gate (mirrors CI) runs over the combined per-unit coverage.
- Per-unit JUnit reports are retained as compliance evidence and staged only if the run is complete and green.
- CI runs the entire suite serially on every push and is the authoritative gate.

## What would newly, permanently exist

A persisted per-run "resume state" (outcome, test report, pytest cache, coverage data and
a content hash of every Python/config file per test unit) that the next gate invocation
of the same run reads to decide what must re-run. The gate code keeps it correct; the
state is deleted when a run is fully green and pruned to the newest few runs.

## Options on the table

- **A:** In-run only: retry just the red tests (instead of the whole unit) after a parallel failure.
- **B:** A plus cross-invocation resume bounded to small changes (few files, no config/conftest change).
- **C:** A plus cross-invocation resume with no bound on what changed.
- **D:** Do nothing; accept ~20 min re-runs.

## Constraints that are not negotiable

- CI stays the authoritative full gate; `.github/**` is not touched.
- The evidence stager requires every unit to carry a complete, green report.
- The coverage gate must never turn a missing measurement into a pass.
