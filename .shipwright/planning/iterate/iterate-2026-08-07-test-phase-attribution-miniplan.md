# Mini-plan: test-phase-attribution

- **Run ID:** iterate-2026-08-07-test-phase-attribution
- **Spec:** `.shipwright/planning/iterate/iterate-2026-08-07-test-phase-attribution.md`
- **Status:** build-ready (opus + 2 rounds external review + operator review incorporated)

## Strategy

Sequenced smallest-blast-radius-first: catalog additions (pure data, no
behavior) land first since everything else imports them; the atomic
resolver primitive lands second in `iterate_timings.py` (testable in
isolation against a synthetic sidecar); the F0-specific attempt policy
(`suite_timing.py`) lands third, depending on the primitive; the
`cpu_budget` relocation + real per-unit `started_utc` land together as
one paired change (the relocation funds the timestamp within the
zero-headroom bloat baseline, so building one without the other leaves
either dead headroom or a baseline breach); per-unit emission lands last,
depending on both the resolver and the real timestamp. Doc/reference
updates land in the same commit as the catalog change they describe
(Registry-driven SSoT rule), not deferred to a cleanup pass.

## Files to change

### Catalog additions (lands first)

| File | Action | Reason |
|---|---|---|
| `shared/scripts/lib/iterate_timings.py` | Edit | `SPAN_PARENTS["f0_unit_result"] = frozenset({"canonical_f0_active"})`; module docstring's "14 nested spans" -> 15; add one clause to the "write path only" docstring noting the new counted-resolution variant. |
| `shared/scripts/lib/iterate_timings_extra.py` | Edit | `EXTRA_FIELD_TYPES["unit"] = (str,)`. `conclusion`/`retry_shape`/`stage` already registered — no change. |
| `plugins/shipwright-iterate/skills/iterate/references/iterate-timings.md` | Edit | Add `f0_unit_result` row to the span table (name, parent, source=producer, extra keys). |
| `docs/hooks-and-pipeline.md` | Edit | Mirror the same row in its own copy of the span catalog. |

### Atomic resolver primitive (lands second, in `iterate_timings.py`)

| File | Action | Reason |
|---|---|---|
| `shared/scripts/lib/iterate_timings.py` | Edit | New `record_producer_span_counted(project_root, run_id, *, name, parent, start_utc, end_utc, duration_ms, outcome, source, extra, count_prior)` — under one `FileLock` acquisition (reusing `_append_line`'s lock/path derivation, not duplicating it): tolerant JSONL read (missing/empty file -> `[]`, never raises), `attempt = count_prior(entries) + 1`, validate + append, return `(path, attempt)` only after the append durably succeeds. `count_prior: Callable[[list[dict]], int]` is caller-supplied policy — this function stays span-shape-agnostic, matching the module's existing scope. This is the corrected mechanism (2nd external review round): an earlier draft assumed `suite_timing.py` could hold `record_producer_span`'s own internal lock from outside — it can't; `_append_line` acquires and releases its own lock, so counting-then-calling-`record_producer_span` was still two separate critical sections. |
| `shared/scripts/lib/tests/test_iterate_timings.py` | Edit | New tests for `record_producer_span_counted`: empty/missing sidecar -> attempt 1 via `count_prior([]) + 1`, `count_prior` receives the tolerant-parsed prior entries, the process-local caller only sees a return value after a durable append (a failing append must not partially write or return). |

### F0-specific attempt policy (lands third, depends on the primitive)

| File | Action | Reason |
|---|---|---|
| `shared/scripts/tools/suite_timing.py` | Edit | Module-level process cache `dict[tuple[Path, str], int]`. Internal helper implementing "whichever of the three wrapper calls is first to have something of its own to write resolves via `record_producer_span_counted` and caches the result; a cached call just does an ordinary `record_producer_span(..., attempt=cached)`" — no separate JSONL read anywhere in this file; the tolerant read lives entirely inside `record_producer_span_counted`. `count_prior` closure: `max(prior_warmup_count, prior_cpu_count, prior_canonical_count)` computed from the entries `record_producer_span_counted` hands it, reading `stage` from each `f0_queue` entry's `extra` (missing `stage` -> counted as `"cpu"`, legacy-entry default). `record_f0_queue_span` gains a `stage: str` parameter, written into the emitted span's `extra` alongside `weight`/`capacity` — not just consumed internally by the counting policy. `record_canonical_f0_active_span`/`_failed` pass `stage="canonical"` internally (not caller-supplied — unambiguous). |
| `shared/scripts/tools/run_test_suite.py` | Edit (0 net lines) | Extend the two existing `record_f0_queue_span(...)` call lines with `stage="warmup"` / `stage="cpu"` kwargs — no new lines, no new call sites. |
| `shared/scripts/tools/tests/test_suite_timing.py` (new or existing) | Create/Edit | AC2 (synthetic N -> N+1), AC7 (orphaned cpu `f0_queue`, no canonical -> N+1 not collide), AC8 (orphaned warmup-only `f0_queue` -> N+1 not collide), AC12 (legacy no-`stage` entry counts as cpu). AC11 (cross-process race) deliberately **not** built as a dedicated test — see spec AC11 for the recorded decision; the lock mechanism itself is still exercised by AC2/AC7/AC8/AC12's real single-process writes. |

### `cpu_budget` relocation + real per-unit `started_utc` (paired change, funds itself within the bloat baseline)

| File | Action | Reason |
|---|---|---|
| `shared/scripts/tools/suite_host_resources.py` | Edit (+2 lines) | Add `cpu_budget(config: SuiteConfig \| None) -> int: return normalize_cpu_weight(config.max_workers if config is not None else None)` — relocated verbatim from `run_test_suite.py`. `SuiteConfig` is already imported here (line 20); `normalize_cpu_weight` is already defined here — zero new imports, no cycle (`suite_units.py` does not import this module). |
| `shared/scripts/tools/run_test_suite.py` | Edit (-2 lines for the function, +1 name added to the existing `suite_host_resources` import block, net -2) | Delete the local `cpu_budget` def (lines 162-163); add `cpu_budget` to the existing `from scripts.tools.suite_host_resources import (...)` block (line 73-75) so `test_run_test_suite_faults.py`'s existing `from run_test_suite import ..., cpu_budget, ...` (line 24) keeps working unchanged — a re-export, matching this file's own established pattern for `suite_units.py` (line 80: "re-export: one import site"). |
| `shared/scripts/tools/tests/test_suite_host_resources.py` | Edit | `test_cpu_budget_is_never_below_one`-equivalent now also covered directly here (it already calls `mod.cpu_budget`, line 35) — confirm no regression, no new test strictly required but add one if the existing coverage doesn't already assert the `config is None` branch `run_test_suite.py`'s copy covered. |
| `shared/scripts/tools/run_test_suite.py` | Edit (+2 lines, net ~0 combined with the relocation above) | Add `started_utc: str = ""` to `UnitResult` (near the existing `unit_id`/`outcome`/... fields); in `_one()` (around line 310, right where the existing `_emit_unit_event(..., event="start", ...)` call already fires), capture `started_utc = datetime.now(timezone.utc).isoformat()` and pass it into the `UnitResult(...)` constructor call — `datetime`/`timezone` already imported (line 40), no new import. |
| `shared/scripts/tools/tests/test_run_test_suite_faults.py` | Edit | New/extended test asserting `UnitResult.started_utc` is populated and distinct across units run in the same `run_suite()` call (not identical timestamps) — the concrete evidence that this is a real per-unit measurement, not a shared anchor. |

### Per-unit emission (lands last, depends on the resolver + the real timestamp)

| File | Action | Reason |
|---|---|---|
| `shared/scripts/tools/suite_timing.py` | Edit | Inside `record_canonical_f0_active_span`, after the existing parent-span write, iterate `result.results` and record one `f0_unit_result` span per `UnitResult` (parent=`canonical_f0_active`), in its own nested `try/except` so a shape mismatch there never also loses the parent span. `start_utc = unit.started_utc`; `end_utc = min(parse(unit.started_utc) + timedelta(seconds=max(0.0, unit.seconds)), parent_end)` where `parent_end = active_start + result.seconds`. `outcome` always `"completed"`; `extra={"unit": ..., "conclusion": ..., "retry_shape": ...}` (`retry_shape` omitted when absent; over-length `unit` degrades that one span only — AC13). `record_canonical_f0_active_span_failed` unchanged (no `result.results` to read on that path — AC4). |
| `shared/scripts/tools/tests/test_suite_timing.py` | Edit | AC3 (normal-return unit spans attach correctly under fold, `start_utc` matches `unit.started_utc` not the parent's), AC4 (`_failed` path emits no `f0_unit_result`, does not raise), AC9 (fresh subprocess with only `shared/` on `sys.path` — matches the real F0 process; a same-process splice can leak pytest's own already-imported modules and false-green), AC13 (over-length `unit` degrades only that span), closed-vocabulary validation of the new `unit` field. |

### Docs / AC verification (lands with each change above, not deferred)

| File | Action | Reason |
|---|---|---|
| (no new file) | — | AC1 verified live via this run's own F0 at finalization, not a code change. AC5 verified by grep/diff across the three doc locations in the same commit as the catalog change. AC10 verified by the pre-commit anti-ratchet hook passing without a baseline bump (not a literal `wc -l == 518` — the relocation + timestamp are designed to net near-zero, not necessarily identical). |

## Test strategy

- **TDD red-then-green per AC**, in the sequencing above.
- **Boundary probe** (`touches_io_boundary`): a real sidecar file on disk,
  written by the actual resolver + emission code, read back by
  `iterate_timings_normalize.fold_into_event` (not a hand-built dict) —
  proves the producer/consumer contract end to end, not just that each
  side individually validates its own shape.
- **Import-path probe** (AC9): a genuinely fresh subprocess with `sys.path`
  set to only `shared/`, matching the real F0 process — this is the
  specific landmine the plan review found and unit tests alone cannot
  catch; a same-process splice risks a false green via leaked module
  objects (external-review finding).
- **Concurrency:** the atomic-resolver lock mechanism is kept and
  exercised indirectly by every real single-process test above (AC2/AC7/
  AC8/AC12 all go through `record_producer_span_counted`'s actual lock).
  A dedicated two-OS-process synchronized test (what AC11 would have
  been) is deliberately not built — see spec AC11 for the recorded
  decision not to spend that engineering weight proving safe degradation
  of a configuration (`F0.md`'s STOP-before-retry protocol structurally
  prevents concurrent F0 for one `run_id`) that cannot occur in
  production.
