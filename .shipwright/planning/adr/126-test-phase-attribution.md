# Producer-stamped attempt number + real per-unit timeline for the test phase

- **Run-ID:** iterate-2026-08-07-test-phase-attribution
- **Date:** 2026-08-07
- **Spec:** `.shipwright/planning/iterate/iterate-2026-08-07-test-phase-attribution.md`

Long-form detail for the decision-drop of the same run id. The drop carries the
terse body; everything a future reader would otherwise have to reconstruct from
commits lives here.

## Context

The `test` phase is 23% of instrumented iterate wall-clock (83 runs) — median
16.9 min, p90 5.3 h, max 34 h. #551's `f0_queue`/`canonical_f0_active` spans
record one suite-level duration per whole-suite invocation, with no way to tell
"the suite is slow" from "it ran four times because tests failed three times",
and no per-unit breakdown at all. The tail was therefore un-diagnosable.

## Decision

Every `f0_queue`/`canonical_f0_active` write resolves `attempt` from the
sidecar's own prior entries, atomically, via a new `record_producer_span_counted`
in `iterate_timings.py` (tolerant read + count + append under one `FileLock`).
`suite_timing.py` supplies the counting *policy* as a `count_prior` closure
taking `max()` across warmup/cpu/canonical stage counts, so a process crashed
mid-attempt cannot collide with the next real one. `record_canonical_f0_active_span`
also emits one new `f0_unit_result` span per test unit, carrying a real
`started_utc` captured in `run_test_suite.py`'s `_one()` right where
`budget.acquire()` returns.

## Rationale

**Why the primitive lives in `iterate_timings.py`, not `suite_timing.py`.**
`record_producer_span` acquires and releases its own `FileLock` internally inside
`_append_line`. A caller that counts first and then calls it has already let go of
the lock between the count and the write — the exact two-step race the design
exists to close, merely relocated. Holding that lock from outside would mean
duplicating lock-path derivation (fragile) or breaching `suite_timing.py`'s
import-path constraint. Colocating the counted variant with `_append_line`, in
the one module already allowed to own lock mechanics, was the only shape that is
actually atomic.

**Why three counts, not two.** `uv_warmup_lease` writes its `f0_queue` span, then
the process can block in `f0_cpu_lease`'s strict-FIFO wait — exactly the
multi-hour queueing this change exists to measure, and therefore the largest kill
window. A process killed there leaves a warmup span at attempt N with no cpu or
canonical span; counting only cpu+canonical would compute `max(0,0)+1 = N` and
collide with the very entry meant to be recovered from. `stage` is therefore
written into the emitted span's `extra`, not merely used internally while
counting — a `stage` threaded only into the counting policy would leave every
future read unable to classify the entries this invocation just wrote.

**Why `started_utc` is a real timestamp rather than the parent's anchor.** An
earlier draft anchored every unit at the parent's `active_start`. That is a
fabrication written as measured data into a git-tracked file: under it, every
child interval starts at the same instant, the union collapses to
`[start, start + longest_unit]`, and `canonical_f0_active.exclusive_ms` silently
reduces to `suite_ms - longest_unit_ms` — an artifact a future reader (or the
deferred latency follow-up) would mistake for real uncovered suite time. Operator
review rejected leaving that in place behind a prose caveat, since the caveat does
not travel with the row. The real timestamp was funded net-zero against the
zero-headroom bloat baseline by relocating the 2-line `cpu_budget()` passthrough
into `suite_host_resources.py`, where it belongs.

## Consequences

A re-run is visible as a re-run directly in the row, without new query tooling.
Legacy `f0_queue` entries with no `stage` key count as `cpu` (back-compat;
verified against all 15 real pre-existing entries, whose counts are unchanged).
Per-attempt span count roughly triples (~18 units add ~18 `f0_unit_result` spans
per attempt), so a jump in `span_count` in the rolling throughput report after
this lands is the new normal, not a regression. `f0_unit_result` is deliberately
absent from `iterate_throughput_render.py`'s `_NESTED_CALLOUTS` allowlist — one
row per unit per attempt would flood the table before any view exists to make it
useful — and that omission is now a comment at the allowlist plus a pin test,
not only prose here.

## Rejected alternatives

- **Deriving attempt ordinals at query time** instead of stamping them. Both
  architecture reviewers (openai, deepseek) converged on this independently. See
  the reconciliation below.
- **A rendered "attempt N of M" throughput view** — no data exists yet to render
  it against; premature until real multi-attempt runs accumulate.
- **Raising `max_workers` / widening the xdist allowlist** — already measured; the
  17-failure regression is documented in `shipwright_test_config.json`.
- **A dedicated multi-process test of F0-level fold-attribution (AC11)** — see the
  scope boundary below.

## Architecture review (`external_review.py --mode architecture`, over a brief)

- **openai:** `revise`, medium. `canonical_f0_active` already gives one durable,
  ordered instance per invocation, so a persisted `attempt` duplicates an ordinal
  a reader could derive from event order.
- **deepseek:** `revise`, high. Same core finding — the counted resolver, the
  three-stage policy and the legacy-`stage` default are avoidable permanent
  write-path machinery.
- **Contradiction check:** none; both converged independently.

**Reconciliation (operator decision, with the withheld plan context back in
scope) — keep the built mechanism.** Two things the brief format necessarily
withheld change the calculus. (1) The stated goal is *row-level visibility*, not
query-time derivability: legible directly in `shipwright_events.jsonl` without
first building a reader that counts prior instances per run — a reader that does
not exist and is an explicit non-goal this run. Dropping the stamp would ship
strictly less of the run's own goal, not the same goal more cheaply. (2) The
`FileLock` is not single-purpose scaffolding: it is the same primitive
`record_producer_span` already uses for every write to this sidecar, and it makes
the read-then-append atomic independently of whether an attempt field exists. The
AC7/AC8 orphan-recovery logic the reviewers flagged is real complexity, and it is
what buys the row-level guarantee. Both findings are logged as
considered-and-declined, not dropped silently. No code change from this pass.

## Review cascade dispositions

**Plan review round 4 (post-build, over the finished spec/mini-plan).** deepseek
approved; openai returned `revise` with 7 findings. Two were real and fixed: a
spec-prose sentence contradicting the actual `started_utc` capture point; and a
missing cross-process proof that `record_producer_span_counted` itself serializes
across real OS processes (distinct from the AC11 F0-level scenario) — added
`test_record_producer_span_counted_serializes_across_real_OS_processes`. A third
gap, no real-execution assertion that `_one()` populates a valid `started_utc`
(every other test hand-builds the fixture), was closed by
`test_unit_results_carry_a_real_started_utc_from_the_actual_dispatch`. The other
four (deadlock risk in a lock-inside-lock call, unguarded empty-`started_utc`
parse, unhandled malformed JSONL lines, `unit` field trust) were already correctly
handled in the code as built — verified against the implementation, not assumed.

**Code review (internal Stage 1/2 + external cascade), all accepted and fixed.**
An unguarded `getattr`/iteration over `result.results` could abort a passed F0 run
on a shape mismatch — wrapped in the module's existing best-effort pattern.
`record_producer_span_counted` duplicated `_append_line`/`record_producer_span`'s
write internals — extracted shared `_span_obj`/`_write_line_unlocked` helpers, no
lock-inside-lock. The render allowlist silently excluded the new span with no
comment recording the decision — documented at the allowlist plus a pin test, and
the spec's "renders generically" claim corrected. `end_utc` was clamped to the
parent interval but `start_utc` was not, permitting an inverted interval under
clock skew (found independently by the internal *and* external reviewers) — both
ends now clamp. The external review's own suggested cross-process test had no
delay inside the locked section and could pass by scheduling luck even against a
broken lock — a deliberate sleep inside `count_prior` makes the proof
deterministic. Two low-severity cleanups taken: dropped a `cpu_budget` re-export
that existed only to spare a one-line test edit, and renamed `_resolve_attempt`
for what it actually does (writes a span, not just looks up a number).

**Doubt review (Stage 3), 5 doubts, all addressed.** The serial-retry loop
(pre-existing, unmodified by this run until now) never wrote the retry's own
wall-clock back onto `UnitResult` and set `retry_kind` only on the
retry-*succeeded* branch — so every retried unit's `f0_unit_result` span would
have covered only its first, failed execution, and a unit that failed twice would
show no sign of having been retried at all. That is the dominant real-world shape
of the very tail this run exists to explain, so it was **fixed, not disclosed**:
`res.seconds` now accumulates the retry's own duration and `res.retry_kind` is set
unconditionally once a retry occurs. Two doubts corrected the *reasoning* behind
the already-declined AC11 decision without reopening it (see below). A
defensive-coding gap — a hand-corrupted sidecar line with a non-dict `extra` could
crash every subsequent attempt-resolution in a run, not just one call, since it
runs inside the resolver's own lock — was fixed with a type guard. One
low-severity timing bias (`parent_end` under-reporting the true suite end by a
fixed setup delta) was rebutted rather than fixed: the proper fix would reopen
`canonical_f0_active`'s already-hardened span semantics for a bias both the
reviewer and the spec characterize as small.

## Scope boundary — concurrent F0 for one run id (AC11)

`record_producer_span_counted`'s lock ensures two concurrent processes cannot
silently collide on an attempt *number*, and that property is verified
cross-process. What is **not** built is a dedicated multi-process test of
*fold-attribution* — whether `f0_unit_result` children attach to the correct one
of two truly overlapping `canonical_f0_active` instances, since the existing
containment matcher (`iterate_timings_normalize.py`, untouched by this diff) has
no attempt-aware disambiguation.

**Corrected by doubt review:** two attempts are usually serialized by host
CPU-lease capacity — `f0_cpu_lease` blocks the second grant while
`2 * weight > hardware_cpu_budget()` — *not* by `F0.md`'s STOP-before-retry
protocol, which governs agent behavior and says nothing about a detached,
still-running prior process. At this repo's `max_workers: 11` that holds below
`cpu_count ~26`; on a bigger host, or from a detached process, two intervals could
genuinely overlap. The gap is unchanged and was already disclosed — only the
reason it is rare is corrected, from "structurally impossible" to "usually
prevented by resource contention". A real fix would thread `attempt` into the
containment search, out of scope here (import-path + bloat boundaries) unless
concurrent F0 is ever intentionally introduced.

## Post-cascade bloat split

Adding the counted resolver pushed `iterate_timings.py` from 222 to 314 lines, a
new crossing of the 300-line guideline. The two bloat gates disagree by design:
the git pre-commit hook (`anti_ratchet_check.py`) treats an un-baselined crossing
as advisory and exits 0, while the Claude-Code Stop hook
(`bloat_gate_on_stop.py`) blocks it outright — `elif delta == "crossing" and not
in_baseline`. Only the second fired. `CLAUDE.md`'s "Pre-commit hooks" section
describes the first and is easy to mistake for the whole policy.

Resolved by splitting, not by baselining: `SPAN_PARENTS`/`EXTRA_FIELD_TYPES` moved
to `iterate_timings_catalog.py` (79 lines), `iterate_timings.py` fell to 266 and
re-exports for all 11 existing importers, and the two 300+ test files were trimmed
to 300. Editing the baseline to buy headroom would have gamed the gate.

The split landed *after* the spec/code/doubt/external cascade, so it got its own
`code-reviewer` pass (zero findings; behaviour-preserving, re-exports verified
against every call site, no circular import) and a full F0 re-run against the
final bytes — the earlier F0 verdict was discarded the moment the source changed.

## Residual gaps, disclosed

- **Goal 3 (the latency fix) is deferred, not delivered.** The per-attempt /
  per-unit history it needs does not exist retroactively; it accumulates only from
  runs finalized after this lands. Proposing a latency change now would not be
  data-driven, which the WHY explicitly asks not to do.
- **One invisible-attempt gap remains.** A process killed inside
  `uv_warmup_lease`'s own acquisition machinery, before the first span is written
  at all, leaves that attempt with no record — silently missing (skips a number),
  never colliding. Closing it needs the lease acquisition to self-instrument: a
  separate, smaller follow-up.
- **The runner-fault path cannot emit per-unit data.** When `run_suite()` raises,
  the partial `results` are local to that frame and lost at the exception
  boundary. Concrete follow-up: have it attach `partial_results` to what it
  raises.
- **A unit id over the 80-character `extra` bound drops just that unit's span**
  (logged to stderr, siblings unaffected — AC13 makes the degradation observable).
  Every real pytest root here is well under 80 characters.
