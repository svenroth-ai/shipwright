# Mini-Plan: context-cost-meter

- **Run ID:** iterate-2026-08-07-context-cost-meter

Revised after two rounds of external review (plan review + architecture
review, both `revise` from both reviewers, no contradiction) — see the
iterate spec's `## External Plan Review` and `## Architecture Review`
sections for what changed and why. The largest change: no incremental
append-only cache. Every `Stop` firing recomputes the full session summary
from the transcript and overwrites one per-session file.

## 1. Files to create/modify

| File | Change |
|---|---|
| `shared/scripts/lib/model_pricing.py` | new — `MODEL_PRICING` dict + `compute_cost_usd(model, usage) -> tuple[float \| None, bool]` (cost, unpriced) — exact match, then date-suffix-stripped match, then `None`, never a cross-model fallback |
| `shared/scripts/lib/context_cost_core.py` | new — `compute_summary(transcript_path, project_root, run_id=None) -> dict`: full-transcript dedup by `requestId`, phase resolution via `iterate_phase_groups.read_marks` (bounded to on-or-after the run's first mark), per-call + aggregate pricing; `fold_into_event(event, project_root, run_id, summary)` mirroring `iterate_phase_groups.fold_into_event` |
| `shared/scripts/hooks/track_context_cost.py` | new — `Stop` hook: reads `transcript_path` from stdin, calls `compute_summary`, overwrites `.shipwright/compliance/context-cost/<session_id>.json`. Wrapped so any failure logs to stderr and returns 0, never blocking shutdown |
| `shared/scripts/tools/context_cost_summary.py` | new — thin `show --session-id [--project-root]` CLI: reads and pretty-prints the per-session file (used at phase boundaries); no aggregation logic of its own |
| `shared/scripts/tools/context_cost_statusline.py` | new — reads the per-session file, emits one line per Claude Code's statusline stdin/stdout contract. Documented (README/guide) as something an operator points their own `~/.claude/settings.json statusLine.command` at — never auto-registered, same constraint as the readiness check |
| `shared/scripts/tools/context_cost_readiness.py` | new — `autoCompactWindow` + effort-level check, `verify_local.py`-shaped report |
| `shared/scripts/tools/estimate_context_pressure.py` | edit — new **opt-in** `--source context-cost` option reading the current session's file; default stays `toolcall`, existing behavior byte-unchanged |
| `shared/scripts/tools/finalize_iterate.py` | edit — call `context_cost_core.fold_into_event` at F5b alongside the existing `iterate_phase_groups.fold_into_event` call, reading the finalizing session's current summary file |
| `plugins/shipwright-build/hooks/hooks.json` | edit — add `track_context_cost.py` as an additional entry in the existing `Stop` array (alongside `generate_handoff_on_stop.py`); `track_tool_calls.py`'s `PostToolUse` entry in the same file is untouched |
| `docs/hooks-and-pipeline.md` | edit — hooks registry entry for the new (additive) `Stop` hook, artifact-write matrix entry for the per-session summary file and for `work_completed.context_cost`, mandatory in the same diff per CLAUDE.md |
| `shared/tests/test_model_pricing.py` | new — per-token-type pricing, exact/date-stripped/unpriced model matching |
| `shared/tests/test_context_cost_core.py` | new — dedup, phase-boundary attribution, malformed-record handling, fold-into-event (incl. `measured_through`/`measured_at` stamp + populated-case regression) |
| `shared/scripts/tests/test_track_context_cost.py` | new — hook-level: additive registration, overwrite-not-append, non-fatal on a broken transcript, writer/reader session-id parity |
| `shared/scripts/tools/tests/test_context_cost_summary.py` | new — `show` reads and formats the per-session file correctly |
| `shared/scripts/tools/tests/test_context_cost_statusline.py` | new — stdin/stdout contract, missing-file behavior |
| `shared/scripts/tools/tests/test_context_cost_readiness.py` | new |
| `shared/scripts/tests/test_context_pressure.py` | edit — new `TestEstimatePressureContextCost` class for the opt-in mode; existing default-mode tests untouched, still passing |
| `shared/tests/test_context_cost_finalize.py` | new — `work_completed.context_cost` fold is additive, degrades gracefully like `phase_timings`, stamped `measured_through`/`measured_at` |
| `shared/scripts/tests/test_context_cost_integration.py` | new (`cross_component`-mandated) — real hook write → statusline read → `--source context-cost` pressure-estimate read, end to end, no mocking |

**Explicitly NOT touched this run:** `shared/scripts/hooks/track_tool_calls.py`
and its `hooks.json` registration — kept running, unmodified. See the
iterate spec's "Out of Scope".

## 2. Work breakdown

1. `model_pricing.py` — `MODEL_PRICING` table (standard rates, Design
   Notes) + `compute_cost_usd`, pricing each token type at its own rate.
   Test: cost matches hand-computed value per token type per model; an
   exact match prices correctly; a `-YYYYMMDD`-suffixed id resolves via
   stripping; a genuinely unknown id returns `(None, True)` — never another
   model's price.
2. `context_cost_core.py` — `compute_summary(transcript_path,
   project_root, run_id)`: full read, `requestId` dedup, phase resolution
   bounded to on-or-after the run's first `iterate_phase_groups` mark,
   per-call and per-phase/session aggregate pricing (`cost_usd` = priced
   subtotal, `unpriced_calls`, `cost_complete`). Test: multi-record single
   response → one call; call before the first mark → `unphased`, after a
   mark → that mark's phase; a usage record with only
   `cache_read_input_tokens` set prices at the cache-read rate; a malformed
   record (no `requestId`/`usage`/`model`) is skipped and counted, not
   fabricated.
3. `track_context_cost.py` — additive `Stop` hook: reads `transcript_path`
   from the hook's stdin payload, calls `compute_summary`, overwrites
   `.shipwright/compliance/context-cost/<session_id>.json`. Test: firing
   twice on an unchanged transcript overwrites with an identical result
   (no doubling — nothing to double, since it's a full recompute); any
   internal exception is caught, logged to stderr, hook still returns 0.
4. `context_cost_summary.py show` + `context_cost_statusline.py` — read
   and format the per-session file. Test: `show` prints per-phase
   breakdown; statusline script emits one line matching Claude Code's
   contract; both handle a missing file (no `Stop` has fired yet)
   gracefully rather than crashing.
5. `context_cost_readiness.py` — read the Claude Code settings hierarchy
   for `autoCompactWindow`, compare against the active model's context
   window; report effort level. Test: unset → `warn`; above window →
   `warn`; sane → `pass`.
6. `estimate_context_pressure.py` — add `--source context-cost` reading
   `<SHIPWRIGHT_SESSION_ID>.json`, as a sibling of the existing `toolcall`
   source (which stays the default, untouched). Test: new mode reads the
   deduped count at the existing 120/300 thresholds; default-source tests
   from before this iterate still pass unmodified.
7. `finalize_iterate.py` — add the `context_cost_core.fold_into_event` call
   at F5b, reading the finalizing session's current (freshly recomputed)
   summary file. Test: a session with a summary file gets a
   `work_completed.context_cost` block; a run with none leaves
   `work_completed` unchanged (additive, never a hard failure — mirrors
   `phase_timings`).
8. `plugins/shipwright-build/hooks/hooks.json` + `docs/hooks-and-pipeline.md`
   — the additive `Stop` registration and its registry/artifact-write-matrix
   entries, same diff.
9. Integration test (`cross_component` mandatory) — a real-scenario test:
   fixture transcript → hook writes the per-session file → `show`/pressure-
   estimate (`--source context-cost`) read it, asserting the numbers
   compose end to end.
10. Phase-boundary surfacing — **corrected mid-Build:** the skill never
    actually calls `iterate_phase_timing.py summarize` anywhere (checked
    against `phase-timing.md` + the F5b skill reference) — the phase-timing
    fold, like the context-cost fold, is a silent F5b-time read, never a
    live in-run print. `context_cost_summary.py show` is the surfacing
    tool (available to run at any point, mirroring `iterate_phase_timing.py
    summarize`'s own never-auto-invoked existence); the F5b fold documented
    in `F5b.md` is the actual boundary-time surfacing this feature adds,
    parallel to the existing `phase_timings` paragraph there.

## 3. Component hierarchy

n/a — no UI.

## 4. Data model changes

The per-session file (`.shipwright/compliance/context-cost/<session_id>.json`)
is new, gitignored, overwritten state — no existing schema touched. **One
tracked addition:** the `work_completed` event gains an additive
`context_cost` block (calls, context integral, cost, per-phase breakdown)
via `fold_into_event`, following the exact precedent `phase_timings`
already set on the same event — optional field, absent on any run
predating this iterate, no migration needed.

## 5. Test strategy

Unit tests per file above (TDD — tests first), including the
malformed-record, unpriced-model, and pre-first-mark-attribution cases as
first-class, not afterthoughts. One `cross_component` integration test per
the risk-taxonomy requirement, real-scenario (not mocked) across hook →
summary read → pressure-estimate. A `finalize_iterate.py` test proves the
`work_completed` fold is additive and never blocks finalization on a
missing summary file (same non-negotiable as `phase_timings`). No E2E — no
web surface. `Verification` runner in the iterate spec covers the
CLI-surface empirical probes.

## 6. Alternative approach (rejected)

**Considered:** build a new, dedicated phase-marker mechanism for the cost
meter instead of reading the existing `iterate_phase_groups` sidecar —
e.g. a `context_cost_phase_marker.py mark <phase>` the skill would call
alongside the existing `iterate_phase_timing.py mark <group>`.

**Rejected because:** the skill already crosses exactly these five
boundaries (`scope build review test finalize`) and already timestamps
them into a gitignored per-run sidecar for M-Pre-1 wall-clock durations. A
second marker would (a) need its own call site added at every one of those
five points in the skill — duplicate wiring for information the first
marker already carries, (b) risk drifting from the wall-clock view if a
future edit updates one call site and not the other, and (c) cost extra
bloat-budget for a sidecar format that is structurally identical to one
that already exists. Reading `iterate_phase_groups.read_marks()` gets
phase-per-timestamp for free, with the two views (duration-per-phase,
cost-per-phase) guaranteed to agree because they share one source of
truth. Both external reviewers left this call alone in both review rounds.

**Also considered (surfaced by external review, not the author):** an
incremental append-only cache (`session-cost.jsonl`) with a separate
summarizer tool reading it. Originally the primary design; dropped after
both the plan review and the architecture review independently flagged it
as disproportionate standing infrastructure for a transcript this small
and this cheap to re-read in full. See the iterate spec's `## Architecture
Review` section for the full reconciliation.
