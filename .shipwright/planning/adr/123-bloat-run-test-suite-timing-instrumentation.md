# ADR-123: Bloat exception — `shared/scripts/tools/run_test_suite.py` raised to 538-LOC

- **Status:** accepted
- **Date:** 2026-08-04
- **Re-Review-Date:** 2026-11-04 _(check whether the F0 timing instrumentation
  can be extracted alongside the file's other `suite_*.py` sibling modules,
  or whether the file has grown further and warrants that split then)_
- **Incident Reference:** iterate-2026-08-04-iterate-timing-attribution —
  the F0 host-lease queue/active producer-timing instrumentation
  (`f0_queue`/`canonical_f0_active` spans) pushed this already-oversize file
  (491 lines pre-change, no prior baseline entry) past 300 for the first
  time this file is being touched with a size-gated change.

## Context

`run_test_suite.py` is the F0 canonical suite runner: unit discovery, the
parallel process pool, retry/race classification, coverage instrumentation,
and the diff-coverage gate — already 491 lines before this iterate, split
across many sibling `suite_*.py` modules it composes (`suite_budget`,
`suite_coverage`, `suite_process`, `suite_race_triage`, `suite_report`,
`suite_host_resources`, `suite_units`, …) but never itself split, and never
previously baseline-tracked despite being well over 300. This iterate added
`_record_f0_queue_span` (persists `host_resource_lease.LeaseGrant.
waited_seconds`, computed by that module and previously discarded) and a
`canonical_f0_active` producer span recorded around `run_suite()`'s own
timing — 48 net lines, entirely inside `_run_host_leased_suite` and its new
helper, measurement only, no change to F0's pass/fail verdict, retry
authority, or gate ordering.

## Ousterhout Argument

`_run_host_leased_suite` is already a deep module by the file's own
convention: a narrow contextmanager (`root, run_id -> (SuiteResult,
source_before, fingerprint_error)`) hiding the uv-warmup lease, the CPU
lease, and now the timing instrumentation for both. The new
`_record_f0_queue_span` helper is a 19-line, single-purpose function with
one real caller shape (best-effort persistence of an already-computed
value) — splitting it into its own file would add a cross-file import for a
function that exists solely to serve the two call sites already inside this
one contextmanager, trading 19 lines of file size for a new public seam
between two things that only make sense together.

## YAGNI Check

Every added line is exercised: `_record_f0_queue_span` by
`test_f0_queue_span_recorded_for_canonical_run_id`,
`test_f0_queue_span_skipped_for_non_canonical_run_id`,
`test_f0_queue_span_skipped_when_no_wait_occurred`, and
`test_f0_queue_span_never_raises_on_bad_project_root`
(`shared/scripts/tools/tests/test_run_test_suite_timing.py`); the
`canonical_f0_active` recording by the synthetic weight-22 test in
`shared/tests/test_iterate_timings.py`. Nothing speculative — no new suite
behavior, no new CLI flag, no new gate.

## Chesterton-Fence Check

The file's existing shape — one large orchestrator composing many small
`suite_*.py` modules rather than being split itself — predates this ADR and
was never challenged by a prior bloat exception (this file had none). Git
history shows it has grown by accretion of F0's own correctness guarantees
(race retry, diff-coverage gate, interpreter pinning) documented at length in
`F0.md`; the fence for keeping the ORCHESTRATOR in one file while its
concerns live in siblings is the module's own docstring ("the safety net")
and is not being torn down by 48 lines of measurement instrumentation.

## Decision

Raise `shared/scripts/tools/run_test_suite.py` to `current: 538`
(`state: exception`, `adr: ADR-123`). Retire at Re-Review-Date if the file
has not grown further; if the timing instrumentation or another concern has
grown it more, extract a `suite_timing.py` sibling alongside the existing
`suite_*.py` modules, matching the file's own established composition
pattern.

## Consequences

No other consumer operates against this file's line count — it is invoked
as a CLI (`uv run run_test_suite.py`) and imported by
`suite_host_resources.py`'s own probe mode and this iterate's test suite,
none of which are sensitive to its size. Cost of the exception holding past
Re-Review-Date is readability of one already-large orchestrator, unchanged
in kind from before this iterate.

## Rejected alternatives

- **Leave the timing instrumentation out.** Rejected — it is the card's own
  deliverable (F0 queue-vs-active attribution is the canonical example in
  the card's problem statement).
- **Extract `_record_f0_queue_span` into a new `suite_timing.py` sibling
  immediately.** Rejected for now per the Ousterhout argument — 19 lines
  with two call sites inside one contextmanager does not yet justify a new
  cross-file seam; revisit at Re-Review-Date if it grows further.
- **Grandfather the file at its pre-existing 491 without ever gating it.**
  Rejected — the file WAS never baseline-tracked, but this session's own
  Stop-hook gate correctly caught it now that a size-relevant change landed;
  retroactively exempting it would defeat the gate's purpose.

## Addendum (2026-08-05) — the file grew again; extracted per this ADR's own plan

The `RUN_ID_STRICT` external-code-review fix (importing the shared regex
instead of a `.startswith("iterate-")` prefix check — see the iterate spec's
Out of Scope log) pushed the file from the 538 this ADR documented to 542,
tripping the Stop-hook a second time. Rather than bump `current` again, this
ADR's own Decision section already committed to the answer for exactly this
case ("if the timing instrumentation ... has grown it more, extract a
`suite_timing.py` sibling"), so that is what happened: `_record_f0_queue_span`
and the inline `canonical_f0_active` recording block moved verbatim into
`shared/scripts/tools/suite_timing.py` (63 lines, well under the cap — no
baseline entry needed) as `record_f0_queue_span` /
`record_canonical_f0_active_span`, imported back in by
`_run_host_leased_suite` exactly as the two functions were called before.
Net effect: `run_test_suite.py` drops to **508 lines** (below even the
original 538), `RUN_ID_STRICT`/`_record_timing_span`/`timedelta` imports move
with the code that used them. Baseline `current` updated 538 -> 508. Existing
tests (`test_run_test_suite_timing.py`) re-target the relocated functions —
behavior unchanged, call sites unchanged, still measurement-only.

## Addendum (2026-08-05) — a second external code review round, +10 lines

A follow-up `external_review.py` pass (round 6) found that
`canonical_f0_active` was recorded only on `run_suite()`'s successful return
— a raised exception skipped the recording entirely, losing the one producer
span most useful during exactly the failed runs it exists to explain. Fixed
by wrapping the `run_suite()` call in `_run_host_leased_suite` with a
try/except that records an `outcome="incomplete"` span (via a new
`record_canonical_f0_active_span_failed` in `suite_timing.py`) before
re-raising unchanged. This is control-flow glue belonging in the
orchestrator, not measurement logic — it does not move to `suite_timing.py`.
`current` 508 -> 518. No new file crossed 300; no further extraction
warranted per this ADR's own Re-Review-Date criterion.
