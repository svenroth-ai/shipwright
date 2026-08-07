# Architecture Brief: test-phase-attribution

## The problem

The `test` phase is 23% of instrumented iterate wall-clock across 83 runs, and
highly skewed (median 16.9min, p90 5.3h, max 34h). Today the timing data
cannot say why: a whole-suite re-invocation after a failure writes new
`f0_queue`/`canonical_f0_active` spans that look identical to the first
attempt's, so nobody reading `shipwright_events.jsonl` can tell a run took
5.3h because of one retried unit versus five, or which unit it was. The
existing spans also only report a single suite-level duration, with no
record of which individual test unit (pytest test-root) consumed the time.

## What already exists here

- `iterate_timings.py` already owns the producer-span sidecar file
  (`shipwright_events.jsonl`), its `SPAN_PARENTS` catalog, and the
  closed-vocabulary `extra` bag validation — this is the only module every
  caller may import from at F0 runtime.
- `suite_timing.py` already emits `f0_queue` (queueing wait) and
  `canonical_f0_active` (suite execution) spans from `run_test_suite.py`,
  gated to canonical iterate `run_id`s only.
- `run_test_suite.py` already produces one `UnitResult` per test unit
  (pytest test-root) inside its `SuiteResult`, with per-unit
  outcome/duration, but nothing today reads those into the timing sidecar.

## What would newly, permanently exist

A per-attempt counter derived from the sidecar's own prior entries (no new
state file), stamped onto every span an attempt writes from now on; and a
new span kind, `f0_unit_result`, one per test unit, nested under
`canonical_f0_active`, carrying a real per-unit start time captured at
actual unit-dispatch. Every future `run_test_suite.py` invocation writes
these; any future reader of the timing sidecar (a query script, the WebUI,
a future latency fix) inherits both the attempt field and the per-unit
breakdown as part of the span shape from now on.

## Options on the table

- **A:** Add per-attempt numbering (via a counted, lock-protected resolver
  in `iterate_timings.py`) plus a new `f0_unit_result` span per test unit,
  with a real `started_utc` captured at unit dispatch.
- **B:** Add per-attempt numbering only; leave per-unit timing unrecorded
  and continue reporting only the suite-level duration.
- **C:** Do nothing further — leave `test`-phase attribution at its current
  suite-level granularity, with re-runs indistinguishable from first
  attempts in the data.

## Constraints that are not negotiable

- No change to `max_workers` or the xdist worker allocation (explicit
  non-goal for this run).
- Any new field in a producer span extra must go through the existing
  closed-vocabulary `EXTRA_FIELD_TYPES` validation — no ad hoc keys.
- `suite_timing.py` may only import from `scripts.lib.iterate_timings` —
  the real F0 process puts only `shared/` on `sys.path`.
