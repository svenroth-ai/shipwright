# Iterate Spec: test-phase-attribution

- **Run ID:** iterate-2026-08-07-test-phase-attribution
- **Type:** change
- **Complexity:** medium (operator-directed; classifier returned `small` at
  confidence 0.6 from the history-prior fall-through — under-classified for a
  change that adds new producer-owned fields to `iterate_timings.py`'s closed
  vocabulary and touches the F0 suite runner's core loop, the exact class of
  change `iterate-2026-08-04-iterate-timing-attribution` and
  `iterate-2026-08-05-iterate-timings-derived-parent` were also escalated to
  medium for.)
- **Status:** implemented

## WHY (verbatim scope from the operator)

The `test` phase is 23.0% of instrumented iterate wall clock (83 runs), and
its distribution — not its median — is the problem: median 16.9 min, p90
5.3 h, max 34 h. A single flat `test` bucket cannot distinguish "the suite is
slow" from "the suite ran four times because tests failed three times", so
the tail is currently un-diagnosable.

**Explicitly out of scope / already checked:**
- The F0 suite's own parallelism (`max_workers: 11`, the per-unit xdist
  ALLOWLIST) is already calibrated by measurement — `shipwright_test_config.json`
  documents a prior regression (17 failures nesting xdist under outer fleet
  load) and states never to replace the allowlist with global `-n auto`.
  **This iterate does not touch `max_workers` or the xdist allowlist.**
- #551 (`iterate-2026-08-05-iterate-timings-derived-parent` and its
  predecessor) already landed hierarchical wall-clock attribution with two
  producer spans for this phase — `f0_queue` (host-lease wait) and
  `canonical_f0_active` (the suite's own execution). At the time this run
  started, neither had been confirmed present in a real `work_completed`
  event (the code was 2 days old).

## Goal

1. Verify `f0_queue`/`canonical_f0_active` actually emit into a real run's
   `work_completed.iterate_timings` (not just unit-tested in isolation).
2. Make a **re-run visible as a re-run**: today every `f0_queue`/
   `canonical_f0_active` pair carries `attempt: 1` regardless of how many
   times F0 was whole-suite re-invoked in the same run, and there is no
   per-unit (pytest test-root) breakdown at all — so "test = 5h" cannot be
   decomposed into runtime vs. repetition vs. lease queueing, or into "which
   unit kept failing." Close both gaps.
3. Only once that data exists, and only where it points at a specific cause,
   propose a latency fix (lease wait, repeated full-suite reruns after a
   single-unit failure). **Not** in scope for this run unless the data
   collected in step 2 already exists retroactively — it does not (no
   historical run has per-attempt/per-unit data), so step 3 is deferred to a
   follow-up iterate once a handful of instrumented runs accumulate. Recorded
   as a known limitation below, not silently dropped.

## Investigation — Goal 1 (verify #551 emission)

**Finding, not assumption:** this repo dogfoods its own iterate pipeline, and
`shipwright_events.jsonl` already contains 15 real `work_completed` events
since 2026-08-05 with correctly-nested `f0_queue`/`canonical_f0_active` spans
(`source: "producer"`, `parent: "verification"`, plausible durations) — e.g.
`iterate-2026-08-06-triage-backlog-outbox-routing`. Base emission is
confirmed working in production, contrary to the "unverified" premise this
run started from. Code-path confirmation: `run_test_suite.py`'s
`_run_host_leased_suite` (lines 420-453) calls
`record_f0_queue_span`/`record_canonical_f0_active_span(_failed)`
(`suite_timing.py`) unconditionally on every F0 invocation under a real
`RUN_ID_STRICT`-shaped run id. This run's own F0 (mandatory at finalization)
re-confirms it live, one more data point, per the Confidence Calibration
section below.

**Real, confirmed gap:** every occurrence of these spans across all 15 runs
carries `attempt: 1` — including runs where 2-3 `f0_queue`/`canonical_f0_active`
pairs appear in one `work_completed.iterate_timings` array (i.e. F0 ran more
than once in that run). The `attempt` field exists in the schema
(`record_producer_span(..., attempt=1, ...)`) but nothing currently populates
it above the default. This is exactly the "un-diagnosable" gap the WHY names.

**Retry model (why this changes `run_test_suite.py`, not the SKILL):** two
retry layers already exist entirely *inside* `run_test_suite.py`'s single
process — a failing unit is re-run serially without xdist, and a
transient infra fault is retried once with the identical shape (lines
~340-397) — neither touches the timing spans, both stay inside one
`f0_queue`/`canonical_f0_active` pair. There is **no in-process whole-suite
retry**. `F0.md` (skill reference) instructs the agent to STOP on any unit
failure and fix the cause before re-entering F0 — a **fresh process
invocation** of `run_test_suite.py` is what happens on the next attempt, from
outside. Because every "attempt" boundary is therefore a fresh process, the
attempt number must be *self-discovered* by that fresh process (read what's
already in this run's own sidecar and count), not carried in by the agent —
consistent with the whole `iterate_timings` design philosophy of moving
measurement burden off agent memory (`iterate-timings.md` §"Why a second
system").

## Design — Goal 2

**Revised after Opus plan review** (`opus-plan-reviewer`, model=opus, run
before build per operator instruction). Two build-blocking findings from
that review are folded in below and are why this section reads differently
from the version the operator's first round of feedback produced:
(a) the original attempt-counter still let two attempts collide across the
*largest* queueing window (the CPU-lease wait itself), not just the tiny
window the operator's own feedback had already closed; (b) `run_test_suite.py`
is in `shipwright_bloat_baseline.json` at `current: 518` and the file is
exactly 518 lines — **zero headroom** — so the design must add no net lines
there, which also fixed an import-path landmine the naive implementation
would have hit (see §2 below).

1. **Attempt auto-numbering** (producer-owned, no agent/SKILL change, no
   added lines in `run_test_suite.py`). **Revised a third time after a
   fresh external LLM iterate-mode review of the updated spec** (2
   providers; deepseek `approve`, openai `revise` with 2 high findings —
   not a contradiction per the tool's own agree-within-one-step check, but
   both real and addressed below). The generalized rule from the prior
   round survives unchanged: all three wrapper functions
   (`record_f0_queue_span` x2 call sites, `record_canonical_f0_active_span`/
   `_failed`) share one policy — before writing, check a process-local
   cache for `(root, run_id)`. Cached -> use that value for this call's own
   write. Not cached, and *this call has something of its own to write* ->
   resolve-and-write atomically (mechanism below), cache the result, then
   proceed. A call whose own skip guard fires (`record_f0_queue_span`,
   `waited_seconds <= 0`) with nothing cached yet simply defers — no
   reservation, no write — leaving resolution to whichever later call in
   the same process is first to actually write;
   `record_canonical_f0_active_span`/`_failed` have no comparable guard
   (unconditional write on both the success and failure paths), so
   resolution is *guaranteed* no later than that call even if both
   `f0_queue` calls skip. This is what makes the design safe regardless of
   which of the three calls happens to go first in a given invocation —
   deliberately not hardcoded to "the warmup call resolves it," which an
   earlier draft got wrong (see the "Resolved, not just documented"
   paragraph below).

   **The atomicity mechanism itself is corrected this round — the prior
   text described something `suite_timing.py` cannot actually do.**
   openai's high-severity finding: `record_producer_span` (the only write
   primitive `suite_timing.py` is allowed to import, per the import-path
   constraint in §3) acquires and releases its *own* `FileLock` internally
   inside `_append_line` — a caller that counts first and then calls
   `record_producer_span` has already let go of any lock between the count
   and the write, which is the exact two-step race this design exists to
   close, just relocated to "inside `suite_timing.py`" instead of "inside
   `run_test_suite.py`." Holding that internal lock across both steps from
   outside is not possible without either reaching into `iterate_timings.py`'s
   private `FileLock` construction (duplicating lock-path derivation —
   fragile, risks a mismatch with `_append_line`'s own path if it ever
   changes) or exceeding the import-path constraint. **Fix: a new,
   narrowly-scoped function is added to `iterate_timings.py` itself**
   (the one module already allowed to own lock mechanics, colocated with
   `_append_line`) — `record_producer_span_counted(project_root, run_id,
   *, name, parent, start_utc, end_utc, duration_ms, outcome, source,
   extra, count_prior)`, where `count_prior: Callable[[list[dict]], int]`
   is the caller's counting *policy* (kept out of `iterate_timings.py`,
   which stays span-shape-agnostic). Under one `FileLock` acquisition it:
   tolerantly parses this run's existing sidecar lines (empty/missing file
   -> `[]`, not an exception — a first invocation must resolve `attempt: 1`
   cleanly, not raise), calls `count_prior(entries)`, sets
   `attempt = count_prior(entries) + 1`, appends the new line (with the
   resolved `attempt` and the caller's `extra`, `EXTRA_FIELD_TYPES`-validated
   exactly like `record_producer_span` already does), and returns
   `(path, attempt)` **only after the append durably succeeds**.
   `suite_timing.py` supplies `count_prior` as a small closure over
   `max(prior_warmup_count, prior_cpu_count, prior_canonical_count)` (its
   own F0-specific policy, per §"Three counts" below) and otherwise reads
   **nothing itself** — the tolerant JSONL read lives entirely inside
   `record_producer_span_counted`, so `suite_timing.py` never needs, and
   must not add, a second, separate read of the sidecar; the process-local
   cache exists purely to skip calling `record_producer_span_counted`
   again once this process already knows its own attempt number (an
   ordinary `record_producer_span(..., attempt=cached)` suffices for that
   fast path, no counting policy involved). The process-local cache is set
   from `record_producer_span_counted`'s return value, so a
   failed append (disk full, invalid extra) never poisons the cache with an
   attempt number that was never durably written — the existing best-effort
   `except Exception` wrapping every `suite_timing.py` call site already
   degrades correctly on that path (skip the span, print to stderr, never
   raise into F0); this call is no exception. `iterate_timings.py`'s "write
   path only" docstring (line 12-14) gets one clause added — "including the
   counted-resolution variant used by producer spans that need atomic
   attempt numbering" — so it does not read as stale once this lands.

   A concurrent second **process** attempting the same sequence blocks on
   `record_producer_span_counted`'s lock until the first has durably
   committed its entry, so it counts one higher and cannot collide; a bare
   in-memory "reserve now, write later" split (release the lock before
   anything durable exists) would not have this property — that was an
   intermediate, incorrect version of this fix from an earlier review round
   and is recorded here only so it isn't reintroduced later.

   **Three counts, not two — the fix to the Opus review's primary
   finding, unchanged this round.** The operator's own round of feedback
   had already caught that counting only `canonical_f0_active` misses a
   process killed between the CPU-lease grant and the `except
   BaseException` boundary. The plan reviewer found the same class of bug
   one layer earlier and larger: `uv_warmup_lease` writes its `f0_queue`
   span, then the process can block in `f0_cpu_lease`'s strict-FIFO wait —
   **exactly the multi-hour queueing this iterate exists to measure**, and
   therefore the single largest kill window of the three. A process killed
   there leaves a warmup span at attempt N with no cpu or canonical span;
   counting only cpu+canonical would compute `max(0, 0) + 1 = N` for the
   next invocation — colliding with the very entry meant to be recovered
   from. **`stage` is written into the emitted span's `extra`, not just
   used internally to pick a bucket while counting** (openai
   medium-severity finding, closing an ambiguity in the prior draft: a
   `stage` threaded only into the counting policy, never persisted, would
   make every future invocation's read unable to classify the very entries
   this invocation is about to write, quietly breaking the three-count
   model one invocation later). `record_f0_queue_span` gains a
   `stage: str` parameter, included in `extra` alongside the existing
   `weight`/`capacity` — a registered `EXTRA_FIELD_TYPES` key already (no
   catalog change needed for `stage`, only for `unit`, per §4).
   **Legacy default:** all 15 real `f0_queue` entries recorded before this
   change carry no `stage` key at all — the counting policy must not crash
   or silently drop them. A missing `stage` is read as `"cpu"`, not
   `"warmup"`: every pre-existing entry is already paired with its own
   `canonical_f0_active` (these are completed historical runs, not
   orphans), so `prior_canonical_count` already reflects them correctly
   regardless of which `f0_queue` bucket they land in, and defaulting to
   `"cpu"` is the conservative choice that changes no observable count for
   any of the 15. In the normal and handled-failure cases all three counts
   are equal (all written in the same invocation, in order) — verified
   against all 15 real production events, where they already agree — so
   `max()` changes nothing observable there. **Residual, disclosed gap
   (unchanged across every round):** a process killed even earlier, inside
   `uv_warmup_lease`'s own lease-acquisition machinery, before that first
   span is written at all, leaves the attempt with no record whatsoever —
   invisible, not colliding. Closing that last gap needs the lease
   acquisition itself to self-instrument, a separate, smaller follow-up
   (see Known Limitations). A `record_producer_span_counted` call that
   itself fails mid-way (lock acquired, tolerant read fails for a reason
   other than a missing file — e.g. a permissions error) degrades to no
   span at all for that call, same as today's `except Exception` pattern —
   never `attempt=1` by default from *this* path (that default only
   applies to the separate, non-counted degrade-on-total-sidecar-failure
   case already documented for `record_producer_span`'s ordinary callers).

   **Resolved, not just documented:** `record_f0_queue_span` already
   returns early without writing when `waited_seconds <= 0`
   (`suite_timing.py:31`, deliberately pinned by an existing test — "zero
   wait is not a span worth recording") — that guard is unreachable in
   practice today (`waited_seconds` is measured across a mutex acquisition,
   a git rev-parse, and a state write, so always > 0), but an earlier
   version of this design (warmup-call-always-reserves) would have quietly
   depended on it staying unreachable. The generalized "whichever call is
   first to actually write" rule removes that dependency by construction —
   any call whose guard fires simply defers, and `canonical_f0_active`'s
   unconditional write is the backstop — so no future change to when the
   guard fires can reopen this collision. AC8 below tests exactly the
   "only a skipped/absent `f0_queue`, resolution falls to a later call"
   shape this generalization exists for.

   **Known, accepted scope boundary (openai's second high finding,
   addressed by disclosure, not by building attempt-aware parenting):**
   this design proves two *concurrent* `run_test_suite.py` processes
   against one `run_id` cannot silently share an attempt *number* (AC11).
   It does **not** attempt to prove that two genuinely concurrent
   `canonical_f0_active` intervals fold-parent their `f0_unit_result`
   children correctly — `_attach_parents`'s existing containment search
   (§5) matches by span name plus temporal window only, with no
   attempt-aware disambiguation, so two truly overlapping
   `canonical_f0_active` instances *could* have a unit-result child
   misattached to the wrong one. This is deliberately out of scope, but
   **the reason two attempts are usually serialized is host CPU-lease
   capacity, not `F0.md`'s STOP-before-retry protocol** — corrected after
   doubt review checked the actual enforcement mechanism rather than
   assuming the agent-facing protocol also *technically* prevents overlap.
   `F0.md` governs what an agent does after a failure; it says nothing
   about a still-alive, detached prior process. What actually blocks two
   F0 processes' CPU phases from running simultaneously is
   `f0_cpu_lease` (`suite_host_resources.py`): each requests
   `weight = min(max_workers, hardware_cpu_budget())`
   (`hardware_cpu_budget() = host_cpus - 2`), and the *second* grant blocks
   in the FIFO wait only while `2 * weight > hardware_cpu_budget()`. At
   this repo's documented `max_workers: 11`, that holds on a host with
   `cpu_count <= 24` (11+11 > cpu_count-2) but **not** on a bigger one
   (`cpu_count >= 26`): both leases could be granted at once, and two
   `canonical_f0_active` intervals could genuinely overlap — from a
   detached, still-running prior process, not from anything the SKILL's
   own calling convention would deliberately start. The gap this leaves is
   unchanged (fold-misattachment on genuine overlap, disclosed above and in
   Known Limitations); what changes is only the accuracy of *why* it is
   rare rather than a claim that it cannot occur. AC11's concurrency is a
   synthetic test of the *lock*, proving the numbering scheme degrades
   safely if the unsupported case ever occurred — not a claim that
   fold-time attribution is also correct in that case. Making
   concurrent-F0 attribution correct would require threading `attempt`
   into the containment matcher itself, a change to
   `iterate_timings_normalize.py` (outside this run's import-path and
   bloat scope) — named here as a follow-up trigger *only if* concurrent
   F0 is ever intentionally introduced, not built preemptively.

2. **Per-unit invocation records — a real per-unit `started_utc`, not a
   shared-start approximation.** Revised once more after operator review
   of this build-ready spec: the previous version anchored every unit in
   an attempt at the same `active_start` (the parent's own start), which
   is a fabrication written as if it were measured data into a
   git-tracked file (`shipwright_events.jsonl`) — the spec disclosed the
   approximation in prose, but that disclosure does not travel with the
   row itself, and a future renderer (or the very latency follow-up this
   run defers) reading `canonical_f0_active.exclusive_ms` would silently
   compute `suite_ms - longest_unit_ms` and mistake it for real uncovered
   suite time. Decision: **spend the real timestamp, not a marker** —
   `_one()` (`run_test_suite.py:306-329`) already captures the moment a
   unit is dispatched, right where it emits its existing `"start"` unit
   event (line 310-311, right after `budget.acquire(...)`); this design
   adds `started_utc: str = ""` to `UnitResult` and sets it there
   (`datetime.now(timezone.utc).isoformat()` — `datetime`/`timezone` are
   already imported at line 40), so each unit gets its own real dispatch
   time instead of inheriting the parent's.
   **Paying for it without breaking the zero-headroom bloat baseline:**
   the field + its one capture line cost ~2 lines in `run_test_suite.py`
   — the bloat policy's own prescribed move at zero headroom is *find
   redundancy, never raise the cap*, and this file already has a
   `cpu_budget(config)` (lines 162-163) that is a pure 2-line passthrough
   to `suite_host_resources.normalize_cpu_weight` — not logic that
   belongs to the *suite runner*, logic that belongs to the *host-resource*
   module already sitting one import away (`suite_host_resources.py`
   already imports `SuiteConfig` from `suite_units.py`, so the move
   introduces no new import and no cycle — verified by reading both
   files' import blocks, not assumed). Relocating it there, matching this
   file's own established `suite_*.py` extraction pattern (ADR-123, the
   same rationale `suite_timing.py`'s docstring already cites), removes 2
   lines from `run_test_suite.py` and adds the same shape to
   `suite_host_resources.py`; `run_test_suite.py` re-exports it through
   the existing `from scripts.tools.suite_host_resources import (...)`
   block (line 73-75), widening one line rather than adding a new one —
   the same "re-export: one import site" pattern the file already uses
   for `suite_units.py` (line 80). Net effect on `run_test_suite.py`'s
   line count: ~0 (−2 for the relocation, +2 for the timestamp),
   comfortably inside the baseline rather than exactly pinned to it.
   `test_run_test_suite_faults.py::test_cpu_budget_is_never_below_one`
   currently imports `cpu_budget` from `run_test_suite` (line 24) — the
   re-export keeps that import working unchanged; only
   `test_suite_host_resources.py` (which already separately tests it via
   `mod.cpu_budget`, line 35) gains the canonical definition.
   **This resolves, rather than merely discloses, the earlier
   shared-start-approximation caveat** — see the revised §5 below.

   **Folded into the existing `record_canonical_f0_active_span` call, not
   a new call site** (unchanged from the prior draft — still the
   bloat-driven relocation that keeps this addition out of
   `run_test_suite.py` entirely). That function already receives
   `result: SuiteResult`, so it already has `result.results: list[UnitResult]`
   — no new parameter needed for *this* part. Inside `suite_timing.py`,
   after recording the parent span, iterate `result.results` and record
   one `f0_unit_result` span per unit (parent=`canonical_f0_active`), in
   its own nested best-effort try/except so a shape mismatch there can
   never also lose the parent span. **This is the success/normal-return
   path, and — checked against the actual code, not assumed — that
   already covers ordinary unit test failures, which is the dominant
   cause of the repeated-invocation tail:** `run_suite()` returns a normal
   `SuiteResult` (`results, 1 if failed else 0, ...` at
   `run_test_suite.py:399-402`) when a unit fails; it does **not** raise.
   Only `SuiteConfigError`, `KeyboardInterrupt`, and genuine
   runner-machinery faults reach the `except BaseException` at line 442 —
   independently confirmed by the plan reviewer against the same lines.
   `start_utc = unit.started_utc` (the real per-unit dispatch time, not
   the parent's); `end_utc = min(parse(unit.started_utc) +
   timedelta(seconds=max(0.0, unit.seconds)), parent_end)` where
   `parent_end = active_start + result.seconds` — **still clamped, now
   against a real start instead of a fabricated one.** The `max(0.0, ...)`
   guards a skew case external review flagged: `UnitResult.seconds` being
   a monotonic-clock difference does not itself rule out a negative value
   reaching here from a future caller or a test double that hand-builds a
   `UnitResult` (the field has no validation of its own) — without the
   floor, a negative `unit.seconds` would compute `end_utc < start_utc`,
   an inverted interval `best_containing_parent`'s containment search does
   not defend against (it only rejects a child ending *after* its parent,
   never one ending *before* it starts). The `min(..., parent_end)` clamp
   still matters even with a real per-unit start: `started_utc` is a
   `datetime.now(timezone.utc)` read taken from inside a worker thread at
   the moment `budget.acquire` returns, and genuinely parallel units under
   xdist each take that read independently — a wall-clock read is not
   perfectly synchronized against the suite's own boundary clock
   (`active_start`/`result.seconds`, read once on the parent's thread), the
   same class of cross-clock disagreement the codebase already handles
   elsewhere (`iterate_timings_pairing.py:91-100`) — the
   clamp makes containment true by construction instead of by argument, at
   the cost of a slightly compressed `end_utc` in the rare skew case
   (acceptable — this is measurement, not a correctness-bearing
   timestamp).

   **Doubt review, rebutted rather than fixed (low severity, accepted):**
   `parent_end` is reconstructed as `active_start + result.seconds` rather
   than read as a real wall-clock moment after `run_suite()` returns.
   `active_start` is captured before `run_suite()` is entered; `result.seconds`
   is measured from a `time.time()` read taken *inside* `run_suite()`, after
   `discover_units`/coverage instrumentation — so `parent_end` under-reports
   the true suite end by that setup delta, and the clamp can shave the same
   delta off whichever unit finishes last. Not fixed: `canonical_f0_active`'s
   own `duration_ms` is the already-reviewed, already-tested measurement of
   suite execution time (`result.seconds`) and changing what `parent_end`
   means would have to either decouple it from that duration (which
   `canonical_f0_active` itself would then also need to adopt, to keep
   children from exceeding a parent end they're supposed to be contained by)
   or thread a second real timestamp through a call site this run has
   otherwise left untouched — real engineering weight for a bias the same
   paragraph above already accepts as "measurement, not correctness-bearing".
   `extra` carries up to three scalars, all within the
   existing closed-vocabulary constraints (`_EXTRA_STR_MAX=80`,
   identifier-shaped, ≤10 keys):
   - `unit` (new `EXTRA_FIELD_TYPES` key, `str`) — the unit id (a path like
     `shared/tests`; matches the existing pattern's allowed charset).
   - `conclusion` (reuses the existing `str` key) — `pass`/`test_failure`/
     `infra`.
   - `retry_shape` (reuses the existing `str` key, omitted when absent) —
     `serial`/`infra`, mirroring `RETRY_SERIAL`/`RETRY_INFRA`.
   Span-level `outcome` is **always `"completed"`** for `f0_unit_result` —
   the span itself (the act of running and reporting a unit) completed
   regardless of the unit's pass/fail verdict, which lives in
   `extra.conclusion` instead. Pinned explicitly (plan-review nit) so the
   render layer's outcome branch is never asked to render a failing test as
   an "incomplete" span.

   **The genuine gap — the runner-fault path — is named, not silently
   dropped:** when `run_suite()` does raise, whatever partial `results` it
   had already accumulated are local to that function and lost to the
   exception boundary today. Concrete follow-up target (not built in this
   run — see Known Limitations): have `run_suite()` attach its partial
   `results` to whatever it raises (e.g. a small `SuiteFault(Exception)`
   wrapper carrying `partial_results: list[UnitResult]`), so
   `record_canonical_f0_active_span_failed` could emit `f0_unit_result` for
   whatever units did finish before the runner faulted.

3. **Import-path constraint (plan-review finding, build-blocking if
   missed):** `suite_timing.py` may import **only**
   `scripts.lib.iterate_timings` (`sidecar_path`, `record_producer_span`,
   and the new `record_producer_span_counted` from §1) — the convention
   already in place at its existing lines 18-19 — and must not reach into
   the read/normalize side for the attempt-counting helper, never
   `iterate_timings_normalize.read_raw_events` or anything from
   `iterate_timings_pairing`/`iterate_timings_synthesis`. Those modules do
   `from lib.iterate_timings import ...` (a bare top-level `lib` package),
   which resolves under pytest's own import machinery (where
   `shared/scripts` ends up on `sys.path` via package `__init__.py`
   discovery) but **not** in the real F0 process, where
   `run_test_suite.py` inserts only `shared/` onto `sys.path`
   (`run_test_suite.py:48`) and `iterate_timings.py` self-inserts only its
   own directory (`iterate_timings.py:41-43`). An in-process unit test of
   the counting helper would stay green while the real F0 entry point
   raised `ModuleNotFoundError` before a single test ran — a CI-blocking
   outage that unit tests alone cannot catch. The Test Completeness Ledger
   (Step 7.5) must include a probe that imports/exercises `suite_timing.py`
   with only `shared/` on `sys.path` (matching the real process), not just
   an in-process pytest import.

4. **Catalog additions**, in `iterate_timings.py`/`iterate_timings_extra.py`
   plus **three** doc/reference locations in the same diff (Registry-driven
   SSoT rule; scope widened by plan review from "the reference docs" —
   there are three, not one, and there is no automated drift guard for this
   catalog the way `gate_catalog` has one): `plugins/shipwright-iterate/skills/iterate/references/iterate-timings.md`'s
   span table, `docs/hooks-and-pipeline.md`'s copy, and the "14 nested
   spans" count in `iterate_timings.py`'s own module docstring (becomes 15).
   `SPAN_PARENTS["f0_unit_result"] = frozenset({"canonical_f0_active"})`,
   `EXTRA_FIELD_TYPES["unit"] = (str,)`. `FOLD_TIME_CAPTURABLE_SPANS` is
   unchanged (it names top-level groups only; a nested grandchild's fold
   reachability is inherited from its top-level ancestor, `verification`,
   already in the list).

5. **Hierarchy fold correctness** (why this is safe to nest a 3rd level):
   `iterate_timings_normalize.py`'s `_attach_parents`/`children_of` grouping
   is parent-**instance**-id based, not depth-limited — verified by reading
   the code, not assumed; independently re-confirmed by the plan reviewer.
   **`canonical_f0_active`'s `exclusive_ms` is a real measurement, not a
   derived artifact — resolved, not just disclosed, by moving to a real
   per-unit `started_utc` (§2 above).** An earlier draft of this design
   anchored every unit at the parent's own `active_start`; under that
   approximation every child's interval started at the same instant, so
   the union collapsed to a single `[start, start + longest_unit]` span
   and `exclusive_ms` reduced to `suite_ms - longest_unit_ms` — an
   artifact of the shared-start fabrication, not real uncovered suite
   time. With each unit's own real dispatch time, `union_duration_ms`
   (`iterate_timings_normalize.py`) computes the actual union of distinct,
   genuinely-overlapping-where-they-really-overlap unit intervals, and
   `canonical_f0_active.exclusive_ms` becomes what it was always supposed
   to be: real suite wall-clock not covered by any unit's own measured
   window (dispatch overhead between units, budget-acquire waits, the
   tail after the last unit completes). `verification`'s own
   `exclusive_ms` is unaffected either way — computed from its *direct*
   children (`f0_queue`, `canonical_f0_active`) only, and the new
   grandchildren never changed that set.

6. **No report/rendering change in this run — checked against the actual
   render code, not assumed.** `iterate_throughput_stats.py` collects
   nested spans generically by name (`nested_by_name`), but
   `iterate_throughput_render.py`'s `_NESTED_CALLOUTS` is a hardcoded
   allowlist gating which nested spans reach a report row — a second span
   registry, out of sync with `SPAN_PARENTS`, with no drift guard (external
   code review). `f0_unit_result` is deliberately **not** added to it: one
   row per test unit per attempt (~18 rows) would flood the table before
   any view exists to make that useful, so the spans are folded and stored
   but stay structurally unrenderable until the deferred latency follow-up
   designs that view (see Known Limitations). The omission is now a code
   comment at the allowlist itself, not only this paragraph. One measurable
   side effect worth stating plainly rather than leaving implicit:
   per-attempt span count roughly triples (~18 discovered units add ~18
   `f0_unit_result` spans per attempt, each a locked sidecar append,
   folding into the git-tracked `shipwright_events.jsonl`) — small in
   absolute cost, but it shifts what `span_count` means in the rolling
   throughput report, so a jump there after this lands is the new normal,
   not a regression.

7. **External review findings addressed by explanation — no design or
   code change.** Three lower-severity findings from the external LLM
   review, each checked against the actual mechanism rather than
   deferred: (a) *parent-instance linkage* — could a synthesized/derived
   `canonical_f0_active` parent from a different attempt wrongly adopt
   this attempt's `f0_unit_result` children? No: `_attach_parents`
   resolves by temporal **containment** against a specific parent
   *instance* (§5 above), and two attempts' `canonical_f0_active`
   intervals never overlap (one process's suite execution finishes, exits,
   before the next process's begins) — a unit span from attempt 2 cannot
   fall inside attempt 1's interval, so the existing containment search
   already prevents cross-attempt attachment without any attempt-aware
   change. (b) *unit-field trust* — should `unit` (a path-shaped string)
   be sanitized beyond the existing closed-vocabulary validation? No:
   `validate_extra`'s existing `_EXTRA_STR_MAX=80` + identifier-charset
   pattern already rejects anything outside `[A-Za-z0-9 ._:/-]`, and the
   value's own source is the pytest-root string this codebase already
   trusts everywhere else it's read (`shipwright_test_config.json`'s own
   unit list) — not user input, no new boundary crossed. (c) *run_id
   cross-contamination* — could two runs' spans mix in one count? No:
   `sidecar_path(root, run_id)` is already one file per run id (existing
   convention, unchanged by this design), so the tolerant read this
   design adds is reading a file that is per-run by construction; there is
   no cross-run filtering to get wrong because there is no cross-run
   data present to filter.

## Architecture Review

Ran `external_review.py --mode architecture` over `architecture_brief.md`
(brief only — no rejection rationale, no file list, no plan) against two
independent models.

- **openai:** `revise`, severity medium. Finding: `canonical_f0_active`
  already gives one durable, ordered instance per whole-suite invocation, so
  a persisted `attempt` field duplicates an ordinal a reader could derive
  from event order; proposed dropping `record_producer_span_counted`, the
  process cache, and `f0_queue.stage`, and assigning attempt ordinals at
  normalization/report-query time instead.
- **deepseek:** `revise`, severity high. Same core finding — the lock-
  protected counted resolver, the three-stage counting policy, and the
  legacy-`stage` default logic are avoidable permanent write-path machinery,
  since sidecar order already recovers attempt sequence for a reader.
- **Contradiction check:** none — both models converged on the same finding
  independently.

**Reconciliation (decided by the operator, with the withheld plan context
back in scope):** keep the built mechanism. Two things the brief format
necessarily withheld from the reviewers change the calculus:

1. **The goal was row-level visibility, not query-time derivability.** Goal 2
   is "make a re-run visible as a re-run" — legible directly in
   `shipwright_events.jsonl`, without first building a reader that counts
   prior `canonical_f0_active` instances per run. That reader does not exist
   and is explicitly out of scope this run (see Non-Goals: "a rendered
   'attempt N of M' throughput-report view — no data exists yet to render").
   Dropping the stamp would mean this run ships strictly less of its own
   stated goal, not the same goal more cheaply — the visibility only
   materializes once a future, unscoped change builds the reader.
2. **The lock is not single-purpose scaffolding for the attempt number.**
   `record_producer_span_counted`'s `FileLock` is the same primitive
   `record_producer_span` already uses for every write to this sidecar; it
   makes the read-then-append atomic, which matters independently of
   whether an attempt field exists. The reviewers' proposal removes
   attempt-numbering's *use* of that safety, not a mechanism built solely
   to serve it.

The AC7/AC8 orphan-recovery logic the reviewers flagged as avoidable
complexity is real, but it is what buys the row-level guarantee: without it,
a process killed mid-attempt would leave an orphaned `f0_queue` that could
collide with the next real attempt's number. Accepting that complexity was
the deliberate trade for stamping the number at write time instead of
deriving it later — recorded here since the brief format is designed to
surface exactly this kind of trade after the fact, not before.

**Outcome:** no code change from this pass. Both findings are logged as
considered-and-declined, not dropped silently.

## Explicit Non-Goals

- Raising `max_workers` or widening the xdist allowlist. Already measured;
  the 17-failure regression is documented in `shipwright_test_config.json`.
- Any change to F0's pass/fail verdict, retry behavior, or gate — this is a
  measurement-only change, identical philosophy to #551.
- A rendered "attempt N of M" throughput-report view — no data exists yet to
  render; premature before real multi-attempt runs accumulate (see below).

## Acceptance Criteria

- [x] AC1: `f0_queue`/`canonical_f0_active` emission is confirmed live in
  this run's own `work_completed.iterate_timings` (F0 at finalization).
  **Confirmed by this run's own F0** (2026-08-07, 18/18 units PASS,
  diff-coverage PASS, exit 0). The run's sidecar
  (`.shipwright/agent_docs/iterates/<run_id>.iterate_timings.jsonl`) carries,
  all `source: "producer"`, all `attempt: 1` (one whole-suite invocation, as
  AC2 predicted a green run must show):
  - `f0_queue` x2 under `parent: verification` — and **both carry the new
    `stage` key in `extra`** (`stage: "warmup"` weight 1/capacity 1;
    `stage: "cpu"` weight 11/capacity 22), which is the Design §1 field the
    three-count policy depends on being *persisted*, not merely used
    internally. Its presence in a real event is what the prior 15 production
    runs could not show.
  - `canonical_f0_active` x1 under `parent: verification`, 289 984 ms.
  - **`f0_unit_result` x18** — the new span — every one attached under
    `parent: canonical_f0_active`, one per discovered test unit, each with
    `extra.unit` + `extra.conclusion` (all `pass` this run; no `retry_shape`,
    since no unit needed a retry).
  - **The per-unit `started_utc` is demonstrably real, not the parent's
    anchor:** the 18 unit spans carry **11 distinct** `start_utc` values
    (units dispatched as fleet capacity freed), so the Design §2 /
    Known-Limitations claim that `exclusive_ms` is now a genuine measurement
    rather than the `suite_ms - longest_unit_ms` artifact of a shared start
    is confirmed against real data, not only against the unit tests.
  - **The fold landed in the durable event, not just the sidecar** (this is
    what AC1 actually asked for): `work_completed.iterate_timings` on event
    `evt-174cc3a7` carries 30 entries — `verification` (agent) with
    `f0_queue` x2, `canonical_f0_active` x1 and `f0_unit_result` x18 nested
    beneath it, 0 rejected.
  - **Direct numeric proof that `exclusive_ms` is now real:**
    `canonical_f0_active` folded to `duration_ms 289984 / exclusive_ms 20343`.
    Under the rejected shared-start approximation the union would have
    collapsed to the single longest unit (`integration-tests`, 245 101 ms),
    forcing `exclusive_ms` to `289984 - 245101 = 44883`. The measured 20 343
    ms is a genuinely different number, so the union really is being computed
    over distinct, partly-overlapping unit intervals — Design §5 verified in
    production, not merely argued.
- [x] AC2: **Verified via unit test over a synthetic sidecar, NOT via this
  run's own live F0** — a synthetic sidecar seeded with N prior
  `canonical_f0_active`/CPU-`f0_queue` entries produces `attempt: N+1` on
  the next call. This run's own live F0 structurally cannot demonstrate a
  second whole-suite attempt: `F0.md` instructs the agent to STOP on any
  unit failure and fix the cause before re-entering F0, so a green run
  invokes F0 exactly once and `attempt` stays `1` for the entire run — a
  second attempt only exists after operator-driven remediation between
  invocations. Recording this explicitly so this run's AC doesn't repeat
  #551's own gap one level up (a claim of "confirmed" that turned out to
  mean "unit-tested," not "seen in a real event").
- [x] AC3: Each `UnitResult` from a normally-returned `run_suite()` call —
  which includes every unit test failure, since failures do not raise — is
  persisted as an `f0_unit_result` span with `unit`/`conclusion` (and
  `retry_shape` when applicable) in `extra`, correctly attached under its
  `canonical_f0_active` parent by the existing fold. `start_utc` is each
  unit's own `UnitResult.started_utc` (captured in `_one()` at dispatch),
  not the parent's `active_start` — a real per-unit timestamp, not a
  shared-start approximation (operator-review finding, Design §2).
- [x] AC4: A run where `run_suite()` itself raises (a runner-level fault —
  discovery/xdist-provisioning/temp-dir failure, not a unit test failure)
  does not attempt to emit `f0_unit_result` spans (no `SuiteResult` exists
  today on that path) and does not raise or break F0.
- [x] AC5: New/changed `SPAN_PARENTS`/`EXTRA_FIELD_TYPES` entries are
  reflected in all three doc/reference locations (`iterate-timings.md`,
  `docs/hooks-and-pipeline.md`, `iterate_timings.py`'s own "14 nested
  spans" docstring count → 15) in the same diff.
- [x] AC6: No existing `iterate_timings` test regresses; new tests cover the
  attempt-counting helper, the per-unit span emission, and the
  closed-vocabulary validation of the new `unit` field.
- [x] AC7: A synthetic sidecar with a CPU-`f0_queue` entry at attempt N and
  no matching `canonical_f0_active` (simulating an OS-level kill between
  the CPU-lease grant and the `except` boundary) produces `attempt: N+1` on
  the next invocation, not a collision with `N`.
- [x] AC8: A synthetic sidecar with only a `stage="warmup"` `f0_queue`
  entry at attempt N — no cpu-lease `f0_queue`, no `canonical_f0_active`
  (simulating an OS-level kill during the CPU-lease wait itself, the
  largest window per the plan review) — produces `attempt: N+1` on the
  next invocation, not a collision with `N`. This is the case the plan
  review found the pre-review design missed.
- [x] AC9: `suite_timing.py`'s new attempt-counting/per-unit-emission code
  imports and runs correctly with only `shared/` on `sys.path` — matching
  the real F0 process, not just pytest's own import resolution — so the
  import-path landmine the plan review found (an in-process unit test
  passing while the real entry point raises `ModuleNotFoundError`) is
  caught by this run's own tests, not discovered in production. **Must run
  in a genuinely fresh subprocess** (a same-process `sys.path` splice can
  leak already-imported module objects from pytest's own resolution and
  give a false green — external-review finding), not merely simulate the
  restricted path inside the test's own interpreter.
- [x] AC10: `run_test_suite.py`'s line count is at or below its baselined
  518 (the redundancy relocation in Design §2 and the new `started_utc`
  capture are designed to net to ~0, not necessarily to land on exactly
  518 — `wc -l` is not asserted equal to a magic number, the pre-commit
  anti-ratchet hook passing without a baseline bump is the actual gate)
  — respected by construction, per the plan review's zero-headroom
  finding. **Measured: 517 lines** (1 under baseline) after the
  `cpu_budget` relocation, the `started_utc` field/capture, and the two
  `stage=` kwarg additions; `ruff check` clean.
- [ ] AC11 — **considered, deliberately not built as a mandatory test**
  (operator decision, recorded per-instruction rather than silently
  inherited from the review that raised it): openai's second review round
  graded cross-process lock contention HIGH and proposed a two-OS-process
  synchronized test proving distinct attempts. The underlying lock
  mechanism (`record_producer_span_counted`, Design §1) is kept — it is
  correctness-load-bearing for the ordinary single-process case too, not
  only the cross-process one, and costs nothing extra to keep. What AC11
  would have been is a dedicated test of *fold-time attribution* under a
  genuinely concurrent two-`run_test_suite.py`-processes-for-one-`run_id`
  scenario — that configuration is explicitly unsupported by this spec
  (§1's "Known, accepted scope boundary", which cites the actual enforcing
  mechanism — host CPU-lease capacity, corrected by doubt review — not
  `F0.md`'s agent-facing protocol). This run exists to *measure* iterate
  wall-clock cost, and a synchronized-multiprocess test of an
  attribution-under-concurrency scenario is real engineering weight
  (deepseek separately flagged flakiness risk on lock-based concurrency
  tests) spent proving safe degradation of a state that is rare rather
  than provably impossible. A HIGH grade from review does not
  auto-ratchet scope. The *primitive's own* cross-process atomicity claim
  is, separately, no longer unverified: a plan-review round after this
  decision found the same class of gap (a subprocess test with no delay
  inside the locked section could pass by scheduling luck even against a
  broken lock) at the primitive level, not the AC11 F0-application-level
  scenario, and
  `test_record_producer_span_counted_serializes_across_real_OS_processes`
  (`shared/tests/test_iterate_timings.py`) was added to close it — real
  `python -c` subprocesses, a deliberate delay inside `count_prior` to
  make the proof deterministic rather than scheduling-lucky, distinct
  attempts asserted. What remains declined is specifically the
  F0-application-level fold-attribution scenario, not primitive-level
  cross-process correctness.
- [x] AC12: A synthetic sidecar containing a legacy `f0_queue` entry with
  no `stage` key in `extra` (the shape of all 15 real pre-existing
  entries) is read without error and counted as `stage="cpu"`, matching
  Design §1's legacy-default rule — not dropped, not misfiled as
  `"warmup"`.
- [x] AC13: A unit id longer than the existing 80-character `extra` string
  bound (an edge case, not expected from this repo's real pytest roots)
  degrades to a skipped `f0_unit_result` span for that one unit only —
  logged to stderr, never raised — while sibling units in the same
  attempt still emit normally, making the degradation explicit and
  observable rather than a silent, untested gap (external-review
  finding).

## Spec Impact

- **Classification:** none
- **NONE justification:** Internal measurement tooling for the Shipwright
  framework's own iterate lifecycle — no product-facing FR, no
  user-observable behavior change for any target project. Same class as
  `iterate-2026-08-04-iterate-timing-attribution` (classified `none`) and
  `iterate-2026-07-11-iterate-phase-timing` (classified `none`), which this
  run directly extends.

## Known Limitations (disclosed, not silently dropped)

- **Goal 3 (latency fix) is deferred, not delivered, in this run.** The WHY
  asks to "cut latency... only where the data points at it" — but the data
  needed (per-attempt, per-unit history) does not exist retroactively; it
  starts accumulating only from runs finalized after this one lands. A
  latency change proposed now would not be data-driven, which the WHY
  explicitly asks not to do. Follow-up iterate once ~10 runs have
  `f0_unit_result`/multi-attempt data.
- ~~Per-unit start-time approximation / `exclusive_ms` derived artifact~~
  — **resolved, not deferred.** The plan-review draft anchored every unit
  at the parent's `active_start` and disclosed the resulting
  `exclusive_ms` distortion as a limitation to accept. Operator review of
  the build-ready spec rejected leaving a fabricated timestamp in a
  git-tracked file even with a documented caveat, and identified a cheap
  paid-for fix: `UnitResult.started_utc`, captured in `_one()` where it
  already emits its "start" unit event, funded by relocating the 2-line
  `cpu_budget()` passthrough into `suite_host_resources.py` (Design §2) —
  net ~0 lines in `run_test_suite.py`. Each unit now gets its own real
  dispatch time; `exclusive_ms` is a real measurement (Design §5).
- **No throughput-report rendering added.** The new data is captured and
  foldable; a human-readable "N attempts, X min queueing, Y min repeated
  runtime" view is left to the follow-up once real data exists to design
  the view against.
- **Attempt numbering has one residual invisible-attempt gap.** A process
  killed during `uv_warmup_lease` itself — before even the warmup
  `f0_queue` span is written — leaves that attempt with no record at all.
  It is silently missing (skips a number implicitly, never seen), not
  colliding with the next attempt's number (the class of bug this run does
  fix, via the `stage`-tagged `max()` counter). Closing the last gap would
  require the warmup-lease acquisition itself to self-instrument before it
  can fail, which is a real producer boundary but a separate, smaller
  follow-up, not folded into this run's scope.
- **Runner-fault path (`_failed`) still cannot emit per-unit data.** Named
  concretely above (Design §2) rather than left as a bare gap: the fix is
  `run_suite()` attaching its partial `results` to whatever it raises. Not
  built here — this run's own per-unit AC (AC3) is satisfiable entirely on
  the normal-return path, which is where the repeated-invocation tail
  actually lives.
- **Concurrent F0 for one `run_id` is unsupported for span
  *attribution*.** `record_producer_span_counted`'s lock ensures two
  concurrent processes cannot silently collide on an attempt number, and
  that specific property is now verified cross-process, not only
  single-process (`test_record_producer_span_counted_serializes_across_real_OS_processes`,
  added after a plan-review round found the original subprocess test
  could pass by scheduling luck rather than actually proving the lock).
  What is **not** built is a dedicated multi-process test of
  *fold-attribution* — whether `f0_unit_result` children attach to the
  correct one of two truly overlapping `canonical_f0_active` instances,
  since the existing containment matcher has no attempt-aware
  disambiguation — a deliberate scope decision (AC11), not an oversight.
  **Corrected by doubt review:** two attempts are usually serialized by
  host CPU-lease capacity (`f0_cpu_lease` blocks the second grant while
  `2 * weight > hardware_cpu_budget()`), not by `F0.md`'s STOP-before-retry
  protocol, which governs agent behavior and says nothing about a
  detached, still-running prior process. At this repo's `max_workers: 11`
  that holds below `cpu_count ~26`; on a bigger host, or from a genuinely
  detached process, two `canonical_f0_active` intervals could overlap.
  The gap itself is unchanged and was already disclosed — only the
  reason it is rare is corrected here, from "structurally impossible" to
  "usually prevented by resource contention, not an intentional
  feature". A real fix would thread `attempt` into
  `iterate_timings_normalize.py`'s containment search, out of scope
  (import-path + bloat boundaries) unless concurrent F0 is ever
  intentionally introduced.
- **A unit id over the existing 80-character `extra` bound silently drops
  just that unit's span** (external-review finding; AC13 makes the
  degradation observable in tests, but no code raises the bound itself).
  Every real pytest root in this repo today is well under 80 characters,
  so this is a defensive edge case, not an active gap — worth revisiting
  only if a future unit id genuinely needs the headroom.

## Post-cascade bloat split (added at finalization, after the review cascade)

Recorded because the diff that ships is **not** byte-identical to the one the
spec/code/doubt/external cascade reviewed, and that must be visible rather than
inferred from the commit.

Adding `record_producer_span_counted` and the catalog entries pushed
`iterate_timings.py` from 222 to 314 lines — a **new** crossing of the 300-line
guideline. Two bloat gates exist and they have deliberately different policies:

- `shared/scripts/hooks/anti_ratchet_check.py` (the git **pre-commit** hook)
  blocks only a ratchet of an entry already in `shipwright_bloat_baseline.json`.
  A new crossing is advisory there — it exits 0. This is what `CLAUDE.md`'s
  "Pre-commit hooks" section describes, and reading that section as the whole
  story is a live trap: it is true of that hook and false of the next one.
- `shared/scripts/hooks/bloat_gate_on_stop.py` (the Claude-Code **Stop** hook)
  additionally blocks a new crossing outside the baseline —
  `elif delta == "crossing" and not in_baseline` (line 274). This one fired,
  three times.

Resolution (operator decision): split rather than baseline the crossing —
consistent with the project rule that a cap is a design constraint and editing
the baseline to buy room games the gate.

- `SPAN_PARENTS` / `EXTRA_FIELD_TYPES` and the catalog header moved to a new
  `shared/scripts/lib/iterate_timings_catalog.py` (79 lines);
  `iterate_timings.py` drops to 266 and re-exports for every existing importer.
- `test_run_test_suite.py` (303) and `test_run_test_suite_faults.py` (302) were
  trimmed to 300 each.
- `test_f0_cli_diff_coverage_e2e.py`'s `_RUNNER_FILES` allowlist gained the new
  module — the one manifest that had to learn about it.

**Verification the split got, separately from the original cascade:** a fresh
`code-reviewer` pass over the split diff alone (zero findings; behaviour-
preserving, all 11 importer call sites covered by the re-exports, no circular
import), `ruff` clean, and a **full re-run of F0** against the final byte
state — the prior F0 verdict was treated as invalidated the moment the source
changed, which is the same fingerprinting principle F0 itself enforces.

## Confidence Calibration

- **Boundaries touched:** `touches_io_boundary` — this change reads/writes
  the `iterate_timings.jsonl` sidecar (JSON) and extends the `extra`
  closed-vocabulary schema.
- **Empirical probes run:**
  - Boundary probe (real producer write → real fold): `test_normal_return_emits_one_span_per_unit_under_the_parent`
    writes real `f0_unit_result` spans via `suite_timing.py` and reads them
    back through the actual `iterate_timings_normalize.normalize_iterate_timings`
    fold (not a hand-built dict) — `rejected == []` confirms the new span
    shape validates and attaches correctly end to end.
  - Import-path probe (AC9): `test_suite_timing_imports_cleanly_with_only_shared_on_sys_path`
    spawns a genuinely fresh `python -c` subprocess with `sys.path`
    restricted to `shared/` (PYTHONPATH stripped, `cwd` outside the repo's
    own import graph) and confirms no `ModuleNotFoundError` — the exact
    shape of the plan-reviewer's landmine.
  - Cross-process atomicity: deliberately **not** probed by a dedicated
    multi-process test — see AC11's recorded decision. The underlying
    `record_producer_span_counted` lock is exercised by every real
    single-process test above (AC2/AC7/AC8/AC12), just not under genuine
    two-process contention.
  - Legacy-data probe (AC12): a synthetic `f0_queue` entry written via the
    plain `record_producer_span` (no `stage` key, matching the shape of
    all 15 real pre-existing entries) is read back by the new counting
    policy without error, counted as `"cpu"`.
- **Test Completeness Ledger:**

  | Behavior | Status | Evidence |
  |---|---|---|
  | Attempt resolves N+1 from synthetic sidecar (AC2) | tested | `test_attempt_resolves_to_n_plus_1_from_a_synthetic_sidecar` |
  | Orphaned cpu-stage `f0_queue` advances, no collision (AC7) | tested | `test_orphaned_cpu_f0_queue_with_no_canonical_still_advances` |
  | Orphaned warmup-stage `f0_queue` advances, no collision (AC8) | tested | `test_orphaned_warmup_only_f0_queue_still_advances` |
  | Legacy no-`stage` entry counts as cpu (AC12) | tested | `test_legacy_f0_queue_with_no_stage_key_counts_as_cpu` |
  | Same-process calls share one resolved attempt | tested | `test_same_process_calls_share_one_resolved_attempt` |
  | Per-unit spans emitted, attached, real `started_utc` (AC3) | tested | `test_normal_return_emits_one_span_per_unit_under_the_parent` |
  | Unit `end_utc` clamped to parent + floored at 0 | tested | `test_unit_end_utc_is_clamped_to_the_parent_and_never_negative` |
  | Runner-fault path emits no unit spans (AC4) | tested | `test_failed_run_never_emits_unit_results` |
  | Over-length `unit` degrades only that span (AC13) | tested | `test_overlength_unit_id_degrades_only_that_span` |
  | Import-path landmine, fresh subprocess (AC9) | tested | `test_suite_timing_imports_cleanly_with_only_shared_on_sys_path` |
  | `record_producer_span_counted` atomic count+append | tested | `test_record_producer_span_counted_*` (5 cases, `shared/tests/test_iterate_timings.py`) |
  | `run_test_suite.py` line count ≤ baseline (AC10) | tested | measured 517/518; `ruff check` clean |
  | Doc/reference locations updated (AC5) | tested | `iterate-timings.md`, `hooks-and-pipeline.md`, and the catalog's own header comment all show 15. The count travelled with `SPAN_PARENTS` into `iterate_timings_catalog.py` when that registry was split out (see "Post-cascade bloat split" below) — it is now colocated with the registry it describes, which is where it belongs |
  | `f0_queue`/`canonical_f0_active`/`f0_unit_result` live in a real event (AC1) | tested | This run's own F0 (18/18 PASS, exit 0): sidecar carries `f0_queue` x2 (both with the new `extra.stage`), `canonical_f0_active` x1, `f0_unit_result` x18 under it, 11 distinct `start_utc` — see AC1 |
  | Cross-process attempt-numbering atomicity of `record_producer_span_counted` (AC11, the part this diff owns) | tested | `test_record_producer_span_counted_serializes_across_real_OS_processes` (real `python -c` subprocesses, deliberate delay inside `count_prior`) |
  | 0 untested-testable — every AC that COULD be exercised pre-finalization is. |
- **Confidence-pattern check:**
  - **Asymptote (depth):** three rounds of adversarial review (Opus plan
    review, two external-LLM passes) each found a real, deeper flaw in the
    attempt-numbering mechanism before build started — same-process
    double-count → warmup-window kill → cross-process race → (this
    session) atomicity primitive misplacement. Depth stopped only when a
    fresh review pass returned no new HIGH finding against the corrected
    mechanism, not on a fixed iteration count.
  - **Coverage (breadth):** every wrapper function touched
    (`record_f0_queue_span`, both `canonical_f0_active` variants) has at
    least one dedicated test; both failure classes (orphaned f0_queue at
    each of the two stages) are covered, not just the happy path; the
    per-unit emission covers pass/fail/retry-shape/clamped-skew/
    over-length in one deliberately varied fixture set rather than one
    shape repeated.
