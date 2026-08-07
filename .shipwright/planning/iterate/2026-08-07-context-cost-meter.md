# Iterate Spec: context-cost-meter

- **Run ID:** iterate-2026-08-07-context-cost-meter
- **Type:** feature
- **Complexity:** medium (floor from `cross_component`: this touches `hooks.json` + a new `shared/scripts/hooks/*.py`)
- **Status:** implemented

## Goal

Measure what a Claude Code session actually costs, straight from the
assistant's own transcript, broken down by which pipeline phase spent it,
and surface that measurement while the session is still running —
replacing a tool-call-count proxy that two prior cost investigations
trusted and both drew a wrong conclusion from, because neither could see
cost broken down by phase.

## Acceptance Criteria

- [x] A `Stop` hook (`shared/scripts/hooks/track_context_cost.py`,
  registered additively in `plugins/shipwright-build/hooks/hooks.json`'s
  existing `Stop` array, alongside `generate_handoff_on_stop.py`) reads
  `transcript_path` in full on every firing — sessions are small (median
  ~276 calls), so a complete re-read is cheap and needs no incremental
  cache, no dedup-recovery machinery, and no cross-process locking.
- [x] Every assistant record is deduplicated by `requestId` (one API
  response is written as N transcript records sharing one `usage` dict —
  undeduped this inflates the call count 1.977x). A record missing
  `requestId`, `usage`, or `model` is skipped with a `skipped_malformed`
  count, never fabricated into a call.
- [x] Per call: `context_tokens` (`input_tokens + cache_read_input_tokens +
  cache_creation_input_tokens`, using the TTL-split `cache_creation.
  ephemeral_5m_input_tokens` / `ephemeral_1h_input_tokens` fields when
  present — never adding both the split and the aggregate) and `cost_usd`
  that prices **each token type at its own rate** (input, output,
  cache-read, cache-write-5m, cache-write-1h are five different numbers,
  never one blended "context_tokens × input rate"; measured cache reads
  were 82% of the actual bill, so blending them is not a rounding error).
- [x] Pricing matches a model id **exactly**, or after stripping a trailing
  `-YYYYMMDD` date-suffix (a versioned snapshot of a known model family —
  not a guess across models). Anything still unmatched writes `cost_usd:
  null, unpriced_model: true` with the raw token counts intact — never
  another model's price.
- [x] Each call carries a `phase` label — `scope | build | review | test |
  finalize | unphased` — resolved from the **existing**
  `iterate_phase_groups` boundary-mark sidecar
  (`<run_id>.phase_timings.jsonl`, written by the `mark scope`/`mark
  build`/... calls the iterate skill already makes) via
  `SHIPWRIGHT_RUN_ID`, never a new marking mechanism. A call with no
  `SHIPWRIGHT_RUN_ID` in force, or timestamped **before** that run's first
  mark, is `unphased` — a transcript spanning more than one run, or
  starting before phase tracking began, must never misattribute a call to
  a run it didn't happen in.
- [x] Each `Stop` firing **overwrites** (not appends) one summary file for
  the current session — the recomputed truth, not an accumulating log —
  keyed by `SHIPWRIGHT_SESSION_ID` so concurrent sessions/worktrees never
  contend on the same file: `.shipwright/compliance/context-cost/
  <session_id>.json`, with the aggregate shaped `{calls, context_tokens,
  cost_usd, unpriced_calls, unpriced_models, cost_complete, by_phase:
  {phase: {calls, context_tokens, cost_usd, unpriced_calls}}}` — `cost_usd`
  at the aggregate level is the sum of what's priced, `cost_complete:
  false` whenever `unpriced_calls > 0`, so a partial total is never
  mistaken for a whole one. `unpriced_models` (added during external code
  review, row 23 below) is the sorted, deduplicated list of model ids that
  produced an unpriced call — bounded and non-growing, it tells an
  operator WHICH model needs a pricing-table entry without resurrecting
  the per-call log design two earlier external-review rounds rejected.
- [x] A phase-boundary summary CLI (`context_cost_summary.py show`) and a
  statusline-compatible script (`shared/scripts/tools/
  context_cost_statusline.py`, documented as something an operator points
  their own `~/.claude/settings.json statusLine.command` at — a plugin
  cannot register into personal settings, same constraint as the readiness
  check below) both read this file directly; no separate
  aggregation-from-cache engine. **Corrected mid-Build:** "phase-boundary
  print" originally implied the skill auto-prints at each boundary — it
  doesn't (verified via grep: the skill never calls a summarize/print step
  at any boundary, only `mark <group>`). `context_cost_summary.py show` is
  the surfacing tool, run manually at any point — the actual, silent,
  F5b-time surfacing is the `work_completed.context_cost` fold below,
  documented in `F5b.md`. This mirrors the precedent `phase_timings`
  already set: no live in-run print exists for that either.
- [x] Each run's totals are folded into the run's tracked `work_completed`
  event at F5b — reading the finalizing session's last-`Stop`-written summary
  file, the same additive, first-write-wins pattern
  `iterate_phase_groups.fold_into_event` already uses for `phase_timings`.
  This is a file read, not a fresh `compute_summary` call: `finalize_
  iterate.py` is a plain script invoked mid-session, not a hook, so it never
  receives a `transcript_path` (that only arrives on a hook's own stdin
  payload) — deriving one from `SHIPWRIGHT_SESSION_ID` alone would mean
  guessing Claude Code's internal transcript-storage layout, the same kind
  of unfounded inference item 3 (below) already rules out for pricing.
  Verified `Stop` fires at every assistant turn end, not once at session end
  (`generate_handoff_on_stop.py`'s own turn-end-skip guard), so the file is
  stale by at most one in-flight turn, never an indefinite lag. The folded
  block is still a **floor, not the whole session** — it cannot include
  F6-F12 (commit, PR delivery, CI rework, the review cascade after F5b) — so
  `fold_into_event` stamps `measured_through: "F5b"` plus the `calls` count
  and a `measured_at` timestamp alongside the totals, so a truncated figure
  can never be compared against a whole-session figure unnoticed.
- [x] `estimate_context_pressure.py` gains an **opt-in** `--source
  context-cost` mode reading the current session's summary file at the
  *same* two thresholds (`builder: 120`, `orchestrator: 300`). The default
  stays `toolcall`; `track_tool_calls.py` and its `hooks.json` registration
  are **left running, unmodified** — this run lands the new hook purely
  additively. Retiring the old proxy is an explicit follow-up iterate, run
  only once real cost data exists to compare the two counts against.
- [x] A readiness check (`context_cost_readiness.py`) reports (a)
  `autoCompactWindow` unset or above the active model's context window, and
  (b) the effort level in force — same report shape (checks list, name +
  status + message) as `verify_local.py`.
- [x] The hook never blocks session shutdown: all logic wrapped so any
  failure logs to stderr and returns 0, matching
  `generate_handoff_on_stop.py`'s own contract. Paths always resolve via
  the shared `resolve_project_root()`, never reimplemented.

## Spec Impact

- **Classification:** add
- **ADD** (new FR appended): FR-01.20 — Context-Cost Meter
- **MODIFY** (existing FR changed): none
- **REMOVE** (FR retired → `## Removed Requirements`): none
- **NONE justification:** n/a

## Out of Scope

- Raw-event or decision-log trimming — both measured at ~0% of session cost
  in `Spec/context-cost-measured.md` Stage 1; the claim that they drive
  cost is falsified (`decision_log.md`: ~25,000 chars total across all 194
  sessions, zero at startup). Not touched by this iterate.
- Changing `autoCompactWindow` or any other Claude Code *setting* — a
  plugin cannot set user settings. The readiness check only **reports**,
  and the statusline script is provided for the operator to wire in
  themselves; neither writes `settings.json`.
- A WebUI surface for the summary file. Statusline + the `context_cost_
  summary.py show` CLI are the only surfaces this iterate builds; a WebUI
  card is a follow-up.
- Re-deriving cost for **historical** sessions already in
  `Spec/measurements/`. This iterate is forward-measuring only.
- Retiring `.shipwright/toolcall_count` / `track_tool_calls.py`, or
  switching `estimate_context_pressure.py`'s default source. This iterate
  lands the new hook and the `--source context-cost` mode purely
  additively, alongside the existing proxy unmodified. Cutover is a
  follow-up iterate, run only once real cost data exists to compare the
  two signals against each other — swapping blind risks the exact
  silent-dead-checkpointing failure `estimate_context_pressure.py`'s own
  docstring already records happening once (producer/reader resolving
  different roots → count 0 → feature dead, unnoticed).

## Design Notes

**Pricing table** (hardcoded `MODEL_PRICING` constant, $/MTok). Base input/
output rates from the `claude-api` skill's Current Models table; cache
economics from `shared/prompt-caching.md` §Economics (cache read = 0.1×
base input; cache write = 1.25× base input for the 5-minute TTL, 2× for the
1-hour TTL — a general multiplier, not per-model):

| Model | Input | Output | Cache write 5m | Cache write 1h | Cache read |
|---|---|---|---|---|---|
| `claude-opus-5` | $5.00 | $25.00 | $6.25 | $10.00 | $0.50 |
| `claude-sonnet-5` | $3.00 | $15.00 | $3.75 | $6.00 | $0.30 |
| `claude-haiku-4-5` | $1.00 | $5.00 | $1.25 | $2.00 | $0.10 |

Decision: **standard (post-intro) rates**, not Sonnet 5's introductory
$2/$10 window, which expires 2026-08-31 — about 3 weeks after this
iterate. A durable meter hardcoding an expiring rate would silently
under-report Sonnet cost from that date on; standard rates instead
over-report by ~33% for the next 3 weeks, the safe direction for a tool
whose purpose is flagging cost pressure.

**Model-id matching: exact, then date-suffix-stripped, then unpriced —
never cross-model.** A real transcript records the versioned id (e.g.
`claude-sonnet-5-20260612`), not the bare family name — matching only the
bare name would leave every real call unpriced. `compute_cost_usd` tries an
exact key match first; failing that, strips a trailing `-YYYYMMDD` (8
digits) and retries — that is recognizing a dated snapshot of a *known*
family, not guessing across models. A model id that still doesn't match
returns `None`; the caller records `cost_usd: null, unpriced_model: true`
with the raw counts. Silently pricing an unrecognized model at another
model's rate is exactly the kind of plausible-but-wrong number that sent
the two prior cost investigations off by 2x — a missing price is visible
and fixable (extend `MODEL_PRICING`); a wrong one looks like data.

**Cost formula prices each token type at its own rate.** `cost_usd =
(input_tokens × price.input + output_tokens × price.output +
cache_read_tokens × price.cache_read + cache_write_5m_tokens ×
price.cache_write_5m + cache_write_1h_tokens × price.cache_write_1h) /
1_000_000`. When only the aggregate `cache_creation_input_tokens` is
present (older transcript shape, no TTL split), it is priced at the
5-minute-TTL rate — the API's documented default TTL when none is
requested — and never summed alongside a split value that isn't there to
double-count.

**No standing incremental cache — recompute in full on every `Stop`,
overwrite one summary file.** The original design (append-only
`session-cost.jsonl`, a separate summarizer reading it, and a
self-deriving dedup-by-reading-itself-back scheme) was reviewed twice —
once as a plan, once as an architecture brief — and both external
reviewers independently converged on the same finding: that is standing
infrastructure disproportionate to the problem, because a session's full
transcript is small (median ~276 calls) and cheap to re-read completely on
every `Stop`. Recomputing fully and overwriting a per-session file instead
of appending to a shared log **also eliminates, by construction, three
separate correctness problems the first plan review had flagged**:
concurrent `Stop` invocations racing on a shared append target (each
session now writes only its own file — no other process ever touches it),
a stale cache being folded into `work_completed` at F5b (the summary is
always freshly recomputed, never a lagging accumulation), and recovering
from a malformed trailing line in a partially-written append log (there is
no append log to corrupt — a bad write is simply overwritten clean next
`Stop`). One shared function (`shared/scripts/lib/context_cost_core.py`,
`compute_summary(transcript_path, project_root) -> dict`) does the
dedup + phase-resolution + pricing and is the single thing the hook, the
statusline script, and the F5b fold all call — never three separate
reimplementations.

**`--source context-cost` is scoped to the current session, matching what
"context window pressure" actually means.** A context window resets per
Claude Code session, not per iterate run (a resumable run can span several
sessions) — so the pressure gauge reads `<SHIPWRIGHT_SESSION_ID>.json`
only, never another session's file.

**Aggregate cost is the known subtotal, with completeness stated
explicitly, never a silent `null`.** A per-call row may honestly be
`cost_usd: null` (genuinely unpriced model). At the aggregate level,
returning `null` for the whole total would throw away every priced call
alongside the unpriced one; summing only what's priced without saying so
would look like a complete number when it isn't. `cost_usd` at every
aggregation level (session total and each phase) is the sum of priced
calls, paired with `unpriced_calls` (count) and `cost_complete: false`
whenever that count is non-zero.

**Statusline is provided, not auto-wired — same constraint as the
readiness check.** Claude Code's status line is a personal `~/.claude/
settings.json statusLine.command`; a plugin cannot register into it any
more than it can set `autoCompactWindow`. `context_cost_statusline.py`
follows Claude Code's statusline stdin/stdout contract and is documented
for an operator to point their own settings at — it is not invoked
automatically by anything in this repo.

## Affected Boundaries

| Producer (writes) | Consumer (reads) | Format |
|---|---|---|
| new `shared/scripts/hooks/track_context_cost.py` (`Stop` hook, additive registration in `plugins/shipwright-build/hooks/hooks.json`) | `context_cost_statusline.py` (operator-wired), `context_cost_summary.py show` (manual, on demand), `estimate_context_pressure.py` (`--source context-cost`) | JSON, overwritten each `Stop`, `.shipwright/compliance/context-cost/<session_id>.json` |
| `iterate_phase_groups.append_mark` (existing, unmodified) | new `context_cost_core.compute_summary` (phase resolution) | JSONL, `.shipwright/agent_docs/iterates/<run_id>.phase_timings.jsonl` |
| new `context_cost_core.fold_into_event` (called from `finalize_iterate.py` F5b) | `work_completed` event consumers (compliance, WebUI) | tracked event field, `context_cost` block on `work_completed` |

## Confidence Calibration

- **Boundaries touched:** the three rows above — the per-session summary
  write/read, the `phase_timings.jsonl` read, and the `work_completed`
  event fold.
- **Empirical probes run:** all 10 executed during Build, green (Test
  Completeness Ledger below carries each probe's actual test name):
  1. Feed the hook a real multi-record transcript fixture (one response
     split across ≥2 records, same `requestId`) — assert exactly one call
     is counted.
  2. Fire the hook twice against the same transcript with no new turns
     between — assert the second run overwrites the summary file with the
     identical result, never doubling anything (recompute is naturally
     idempotent; there is nothing to accidentally double).
  3. Feed a transcript with no `SHIPWRIGHT_RUN_ID` set — assert every call
     lands `phase: "unphased"`, none dropped.
  4. Build a fixture where a call's timestamp precedes the run's first
     phase mark (a transcript that spans into a prior or not-yet-started
     run) — assert that call is `unphased`, not attributed to the current
     run.
  5. Feed a usage record whose `model` is absent from `MODEL_PRICING` in
     both exact and date-stripped form — assert `cost_usd: null,
     unpriced_model: true`, raw counts intact.
  6. Feed a usage record with only `cache_read_input_tokens` set (no plain
     `input_tokens`) — assert `cost_usd` prices that count at the
     cache-read rate, not the input rate (the 82%-of-bill regression this
     design exists to prevent).
  7. Feed a transcript with a versioned model id (`-YYYYMMDD` suffix) that
     matches a known family after stripping — assert it prices correctly,
     not as unpriced.
  8. Run the hook with a `session_id` from stdin that deliberately disagrees
     with `SHIPWRIGHT_SESSION_ID` — assert the write lands under the
     **payload's** value, never the env var's. **Corrected during Stage-2
     code review:** the first cut of this probe asserted the opposite
     (env-first), matching a naive reading of the F10 tool-call-counter
     divergence — but `bloat_gate_on_stop.py`'s own `_session_id` docstring
     already documents, empirically, that `SHIPWRIGHT_SESSION_ID` is NOT
     reliably set in a `Stop`-subprocess's environment (fixed
     `iterate-2026-05-29-bloat-gate-session-id` after env-first pooled every
     session into one shared file). The hook and the statusline share that
     exact process class and must both prefer the payload
     (`context_cost_core.resolve_session_id`); `estimate_context_pressure.py`
     and `finalize_iterate.py` are a different process class — plain
     Bash-tool-invoked scripts with no payload at all — and read the env var
     directly, which is reliable for THEM via `CLAUDE_ENV_FILE`.
  9. Read `generate_handoff_on_stop.py`'s own turn-end-skip guard — confirms
     `Stop` fires at every assistant turn end, not once at session end, so
     the F5b fold's last-written file is stale by at most one in-flight
     turn (see the F5b bullet above for why this rules out attempting a
     fresh `compute_summary` call from `finalize_iterate.py` instead).
  10. Fold a real `compute_summary(...)` result (not an empty/absent one)
      into an event — assert the populated case actually produces non-zero
      `calls`/`cost_usd` and the `measured_through`/`measured_at` stamp, not
      only the graceful-absence path.
- **Test Completeness Ledger:** all 30 rows `tested`, 0 `untested-testable`.

  | # | Testable behavior | Disposition | Evidence / reason_code |
  |---|---|---|---|
  | 1 | Multi-record single response dedups to one call | tested | `shared/tests/test_context_cost_core.py::test_multi_record_single_response_dedups_to_one_call` |
  | 2 | Repeated `Stop` firing overwrites with an identical, non-doubled result | tested | `shared/scripts/tests/test_track_context_cost.py::test_repeated_firing_overwrites_with_identical_result` |
  | 3 | Call outside any run_id is labelled `unphased`, not dropped | tested | `shared/tests/test_context_cost_core.py::test_no_run_id_means_every_call_is_unphased` |
  | 4 | Call before the run's first phase mark is `unphased`, not misattributed | tested | `shared/tests/test_context_cost_core.py::test_call_before_first_mark_is_unphased` |
  | 5 | Cost sums each token type at its own rate (cache-read ≠ input rate) | tested | `shared/tests/test_model_pricing.py::test_cache_read_only_usage_prices_at_cache_read_rate_not_input_rate` |
  | 6 | Unrecognized model id (exact + date-stripped both fail) → `cost_usd: null, unpriced_model: true`, raw counts kept | tested | `shared/tests/test_model_pricing.py::test_unrecognized_model_returns_none_never_another_models_price` + `test_unrecognized_versioned_model_also_returns_none` |
  | 7 | Versioned model id resolves via date-suffix stripping to the correct family price | tested | `shared/tests/test_model_pricing.py::test_versioned_model_id_resolves_via_date_suffix_stripping` |
  | 8 | Aggregate `cost_usd` = priced subtotal; `cost_complete: false` whenever `unpriced_calls > 0` | tested | `shared/tests/test_context_cost_core.py::test_aggregate_cost_is_priced_subtotal_with_completeness_flag` |
  | 9 | Malformed record (missing `requestId`/`usage`/`model`) is skipped, counted, never fabricated | tested | `shared/tests/test_context_cost_core.py::test_malformed_record_is_skipped_and_counted_not_fabricated` |
  | 10 | `estimate_context_pressure.py --source context-cost` reads the current session's file at the same 120/300 thresholds; default source unchanged | tested | `shared/scripts/tests/test_context_pressure.py::TestEstimatePressureContextCost` |
  | 11 | `track_tool_calls.py` and its `hooks.json` registration are unmodified by this diff | tested | `shared/tests/test_context_cost_hook_registration_additive.py` |
  | 12 | Readiness check flags unset/oversized `autoCompactWindow`; effort level reported honestly (`warn` when not passed, never fabricated) | tested | `shared/scripts/tools/tests/test_context_cost_readiness.py` |
  | 13 | `finalize_iterate.py` folds calls/context/cost/per-phase breakdown into `work_completed`, additive like `phase_timings`, stamped with `measured_through`/`measured_at` | tested | `shared/tests/test_context_cost_fold.py::test_fold_into_event_stamps_measured_through_and_measured_at` + `shared/tests/test_context_cost_finalize.py` |
  | 14 | Hook never raises out of `main()` — a broken transcript logs to stderr and still returns 0 | tested | `shared/scripts/tests/test_track_context_cost.py::test_broken_transcript_path_never_blocks_the_hook` + `test_malformed_stdin_never_blocks_the_hook` |
  | 15 | Integration (`category: integration`): hook writes the per-session file → statusline script reads it → pressure-estimate (`--source context-cost`) consumes it, end to end, real files, no mocking | tested | `shared/scripts/tests/test_context_cost_integration.py` |
  | 16 | Writer (`Stop` hook) and same-process-class reader (statusline) resolve the SAME session id via `resolve_session_id` — payload wins when present, env only as fallback — so a stdin payload that disagrees with `SHIPWRIGHT_SESSION_ID` never splits them into two files. **Corrected during Stage-2 code review:** row originally asserted this parity against `estimate_context_pressure.py`, but that script is a different process class (plain Bash-tool script, no stdin payload, env-only by design — see `context_cost_core.resolve_session_id`'s docstring) and was never part of this parity claim | tested | `shared/scripts/tests/test_track_context_cost.py::test_writer_prefers_payload_session_id_over_env` + `test_writer_falls_back_to_env_when_payload_has_no_session_id` + `shared/scripts/tools/tests/test_context_cost_statusline.py::test_reader_prefers_payload_session_id_over_env` + `test_reader_falls_back_to_env_when_payload_has_no_session_id` |
  | 17 | The F5b fold's populated case (real `compute_summary` output, not just absence) actually reaches `work_completed.context_cost` | tested | `shared/tests/test_context_cost_fold.py::test_fold_into_event_populated_case_from_a_real_computed_summary` |
  | 18 | A malformed summary file (non-object JSON, or invalid JSON) never loses the `work_completed` event — `read_summary` degrades it to `no_data`, `read_and_fold_into_event` swallows any error and leaves `event` unchanged. **Added during Stage-2 code review** (BLOCKING: the pre-fix code let an `AttributeError` from a malformed summary propagate out of `_record_event`, dropping the whole event, not just `context_cost`) | tested | `shared/scripts/tools/tests/test_context_cost_summary.py::test_read_summary_treats_a_non_object_json_file_as_no_data` + `test_read_and_fold_into_event_survives_a_malformed_summary` + `shared/tests/test_context_cost_finalize.py::test_finalize_survives_a_malformed_summary_file` |
  | 19 | The Stop hook resolves `run_id` via `phase_quality.pointer_run_id` (the live, session-matched pointer lookup) — never the raw `SHIPWRIGHT_RUN_ID` env var, and never `resolve_run_id`'s broader fallback chain — proven end to end with a REAL git worktree, a real active-run pointer and a real phase mark, asserting the call lands under `by_phase.build`, not `unphased`. **Added during Stage-3 doubt review, narrowed in a follow-up round of the same review:** the env var is documented, one iterate earlier in this same repo, as never reaching a hook-launched subprocess (HIGH: `SHIPWRIGHT_RUN_ID` was always empty in production, so phase attribution was dead on arrival). A first fix landed `resolve_run_id`, which the same reviewer then flagged as introducing a NEW risk — its other fallbacks (`shipwright_run_config.json::run_id`, latest `run_started` event) are project-global and can outlive the run that minted them, so they could misattribute a later, unrelated session's calls to a stale run's last phase (see row 22). `pointer_run_id` alone closes that, since it only ever returns a run_id for a LIVE, THIS-session-matched pointer | tested | `shared/scripts/tests/test_track_context_cost_worktree.py::test_hook_writes_to_the_active_worktree_and_attributes_a_phase` |
  | 20 | The Stop hook's `project_root` resolution prefers the session's active iterate worktree (via the same run pointer) over the naive `resolve_project_root()`, which falls back to cwd — proven with the same real-worktree fixture as row 19, asserting the write lands in the WORKTREE and NOT the main repo. **Added during Stage-3 doubt review** (HIGH: a Stop subprocess's cwd is the MAIN repo even while an iterate runs in a linked worktree, documented precedent in `iterate_stop_finalize.py`; without this, the writer and the F5b reader — which reads from the worktree — silently never agreed on a file during any real iterate run) | tested | `shared/scripts/tests/test_track_context_cost_worktree.py::test_hook_writes_to_the_active_worktree_and_attributes_a_phase` + `shared/tests/test_context_cost_fold.py::test_resolve_active_project_root_prefers_the_pointed_worktree` + `::test_resolve_active_project_root_falls_back_without_a_pointer` |
  | 21 | `.shipwright/compliance/context-cost/` is gitignored (both `.gitignore`'s managed block and `shared/templates/shipwright-gitignore.template` stay congruent), matching every sibling run-scoped sidecar (`*.phase_timings.jsonl` etc.) — without it every turn drops an untracked file into a tracked evidence tree. **Added during Stage-3 doubt review** (MEDIUM-HIGH) | tested | `shared/tests/test_gitignore_template_congruent.py` (drift guard; the new rule line itself is asserted present by that suite's existing congruence check) |
  | 22 | A stale, project-global run id (`shipwright_run_config.json::run_id` from a finished run, with its phase marks still on disk — gitignored, never deleted, and a retained-after-merge worktree still looks live) is never picked up by a later, unrelated session working in that same tree; every call from that session degrades to `unphased` rather than being misattributed to the stale run's LAST phase. **Added during the same Stage-3 doubt-review follow-up round as row 19's narrowing** (the residual risk `resolve_run_id`'s broader fallback chain would have reintroduced — this is the regression guard proving `pointer_run_id` alone actually closes it, not just that the mechanism changed) | tested | `shared/scripts/tests/test_track_context_cost_worktree.py::test_hook_never_misattributes_to_a_stale_finished_runs_marks` |
  | 23 | Unpriced calls record which distinct model id(s) produced them (`unpriced_models`, sorted + deduplicated), not just a bare count — bounded, non-growing, and reaches the persisted `work_completed.context_cost` fold. **Added during external code review** (openai, high) | tested | `shared/tests/test_context_cost_core.py::test_unpriced_calls_record_their_distinct_model_ids` + `shared/tests/test_context_cost_fold.py::test_fold_into_event_carries_unpriced_models_when_present` + `test_fold_into_event_defaults_unpriced_models_when_absent` |
  | 24 | TTL-split cache-write detection keys on the split field's PRESENCE, not its value's truthiness — an explicit-zero split (`{"ephemeral_5m_input_tokens": 0, ...}`) still wins over a nonzero aggregate rather than falling through to it, in both `compute_cost_usd` and `compute_summary`'s own context-token tally. **Added during external code review** (openai, medium) | tested | `shared/tests/test_model_pricing.py::test_ttl_split_present_with_explicit_zero_wins_over_a_nonzero_aggregate` + `shared/tests/test_context_cost_core.py::test_context_tokens_ttl_split_present_with_explicit_zero_wins_over_aggregate` |
  | 25 | A session id that would collide with another on-disk (e.g. containing a path separator) is rejected by the shared `session_summary_path` validator — the write/read is skipped entirely, never derived down to a colliding basename, and a legitimate same-basename session's file is never read back for the crafted id. **Added during external code review** (openai, medium) | tested | `shared/scripts/tools/tests/test_context_cost_summary.py::test_session_summary_path_rejects_an_id_containing_a_path_separator` + `test_read_summary_treats_an_unsafe_session_id_as_no_data` + `shared/scripts/tests/test_track_context_cost.py::test_session_id_containing_a_path_separator_skips_the_write` |
  | 26 | A transiently-missing transcript file on a LATER `Stop` firing (after an earlier firing already recorded real data) never overwrites the prior summary with an empty one — the write is skipped and the last durably-recorded file is left byte-identical. **Added during external code review** (deepseek, medium + low) | tested | `shared/scripts/tests/test_track_context_cost.py::test_missing_transcript_on_a_later_firing_preserves_the_prior_summary` |
  | 27 | A versioned/dated model snapshot id (e.g. `claude-sonnet-5-20260612`) passed to the readiness check resolves via the same exact-then-date-stripped policy `model_pricing.compute_cost_usd` already uses, instead of a bare dict lookup that read a real, live model as "not a known model". **Added during external code review** (openai, medium) | tested | `shared/scripts/tools/tests/test_context_cost_readiness.py::test_versioned_snapshot_model_id_resolves_the_same_as_its_family` + `shared/tests/test_model_pricing.py::test_resolve_model_id_exact_and_date_suffix_stripped` |
  | 28 | Cost is accumulated at full precision through both `compute_cost_usd` and `compute_summary`'s per-phase buckets, rounded exactly once at the point a total is finalized — many sub-microdollar calls (a single cache-read token, below the 6dp threshold) sum to a nonzero total, not zero. **Added during external code review, Round 2** (openai, medium) | tested | `shared/tests/test_model_pricing.py::test_many_sub_microdollar_calls_are_not_individually_rounded_to_zero` + `shared/tests/test_context_cost_core.py::test_many_sub_microdollar_calls_sum_to_a_nonzero_total` + `test_by_phase_cost_is_not_rounded_after_every_addition` |
  | 29 | A `Stop` firing with neither a payload `session_id` nor `SHIPWRIGHT_SESSION_ID` set skips the write entirely rather than pooling under a fixed `"unknown"` placeholder — the same collision class row 25 closed for a crafted id, closed here for the genuinely-absent case. `estimate_context_pressure.py`'s own separate `"unknown"` fallback fixed identically for consistency. **Added during external code review, Round 2** (openai, medium) | tested | `shared/scripts/tests/test_track_context_cost.py::test_hook_skips_the_write_when_neither_payload_nor_env_has_a_session_id` + `shared/scripts/tests/test_context_pressure.py::TestEstimatePressureContextCost::test_no_session_id_at_all_is_no_data_not_a_stray_unknown_file` |
  | 30 | A transcript record with a wrong-TYPE (not merely missing) `requestId`/`model`/token-count field never aborts the whole transcript's accounting — string/unhashable values degrade that one field/record without discarding every OTHER call in the same firing. **Added during external code review, Round 2** (openai, medium) | tested | `shared/tests/test_context_cost_core.py::test_malformed_record_is_skipped_and_counted_not_fabricated[unhashable-requestId]` + `[unhashable-model]` + `test_non_numeric_token_field_does_not_abort_other_calls_in_the_transcript` + `shared/tests/test_model_pricing.py::test_unhashable_model_degrades_to_unpriced_not_a_crash` + `test_non_numeric_token_field_degrades_that_field_to_zero_not_a_crash` |
- **Known limitations surfaced by Stage-3 doubt review, deliberately not fixed this run** (advisory, not blocking — see the run's `reviews.json` for the full doubt-review text):
  - **MEDIUM — a third session-id process class.** `iterate_stop_finalize.py`'s repair-pass fallback calls `finalize_iterate.run()` directly from within its OWN `Stop` subprocess, where `finalize_iterate.py`'s internal `session_id = os.environ.get("SHIPWRIGHT_SESSION_ID", "unknown")` (line predates this feature, unmodified here) is the same env-only read this feature's whole design says is unreliable for that process class. If it reads wrong, the F5b fold degrades to a graceful, already-tested `no_data` skip (row 18) — never data corruption — so this is scoped out rather than fixed, since a correct fix means changing `iterate_stop_finalize.py`'s own payload handling, a different plugin's pre-existing Stop hook, not something this feature's diff should expand into.
  - **MEDIUM — dedup's first-wins-on-duplicate-`requestId` policy is validated only against a synthetic fixture** (`test_multi_record_single_response_dedups_to_one_call` passes the identical `usage` dict twice, so it cannot distinguish first-wins from last-wins). Follow-up: confirm against a real transcript that a duplicated `requestId`'s `usage` field is in fact identical across records before this assumption is load-bearing for a real cost figure.
  - **Bounded — a resumed session whose id no longer matches the B1a run pointer** (written once, keyed by session id; this spec's own AC9 notes "a resumable run can span several sessions") degrades `pointer_run_id` to `None` and `resolve_active_project_root` to the main tree for the remainder of that run — never wrong data, just `unphased` calls and a summary filed under main instead of the worktree. Same bound `iterate_stop_finalize.py`'s repair pass already accepts in the identical situation (refuses and prints a diagnostic rather than guessing); not a regression this feature introduces.
- **Confidence-pattern check:**
  - **Depth (asymptote):** two rounds of external review before any code
    existed (plan + architecture), each surfacing a real, non-cosmetic
    finding the other round didn't (the incremental-cache design in
    architecture review; hooks.json/statusline naming + pricing precision
    in plan review) — plus a mid-Build user correction that caught two
    correctness gaps no reviewer had (F5b's `measured_through` staleness
    ambiguity, and the writer/reader session-id divergence risk that is
    this exact repo's own documented F10 failure class). Three independent
    passes, three distinct real findings each — not diminishing returns
    yet, so this is not asserting "done", just "still finding real things,
    still worth another pass if one is requested."
  - **Breadth (coverage):** all 17 Test Completeness Ledger rows `tested`,
    0 `untested-testable`; the 3 Affected Boundaries rows below each have
    ≥1 dedicated test plus the end-to-end integration test (row 15)
    exercising all three together on real files, not mocked in isolation.

## External Plan Review

- **Provider:** openrouter (deepseek + openai), Branch A.
- **Verdicts:** deepseek=revise · openai=revise (no contradiction — both
  agree within one step).
- **Findings integrated:** exact `hooks.json` file identified
  (`plugins/shipwright-build/hooks/hooks.json`, `Stop` array, additive) ·
  statusline file named and its non-auto-wired nature documented · phase
  attribution bounded to on-or-after the run's first mark (calls before it
  are `unphased`) · model-id matching made exact-then-date-suffix, never
  cross-model · malformed-record handling specified (skip + count, never
  fabricate) · aggregate cost/completeness schema specified
  (`cost_usd`/`unpriced_calls`/`cost_complete`) · canonical
  `resolve_project_root()` reuse made explicit · hook wrapped
  non-fatal, matching `generate_handoff_on_stop.py`'s own contract ·
  cache-write aggregate-vs-split extraction rule specified (prefer split;
  aggregate-only prices at the 5m default TTL, never double-counted
  against a split that isn't present).
- **Findings obsoleted by the architecture-review simplification (below),
  not separately patched:** concurrent-`Stop`-race on a shared cache file
  · stale cache folded into `work_completed` at F5b · malformed trailing
  line in an append-only log. All three assumed the incremental-cache
  design; recompute-and-overwrite-per-session removes the shared mutable
  state each depended on.

## Architecture Review

- **Brief:** `.shipwright/planning/iterate/iterate-2026-08-07-context-cost-meter/architecture_brief.md`
- **Verdicts:** deepseek=revise · openai=revise
- **Smallest thing that would do (per reviewers):** one shared
  transcript-parsing/pricing function, invoked directly by the statusline
  and finalize paths, with no standing append-only cache or separate
  aggregator tool — the finalized aggregate still folds into
  `work_completed`.
- **Findings:**
  - The incremental JSONL cache + separate summarizer + self-healing
    dedup-by-reading-itself-back is standing infrastructure disproportionate
    to a small, cheaply-re-readable transcript — **accepted and fixed**:
    replaced with full recompute + overwrite of one per-session file on
    every `Stop`, per the Design Notes above.
  - (openai, low) the readiness check adds a standing settings-interpretation
    mechanism that doesn't measure cost and can't remediate what it
    reports — **rejected, kept**: it is item 5 of the operator's original
    brief for this feature, an explicit requirement, not a follow-up; one
    reviewer's low-severity proportionality note doesn't override that.
  - (deepseek, low) folding into `work_completed` "is useful... but not
    needed for the immediate goal... can be a follow-up" — **rejected,
    kept**: the operator's correction round on this same mini-plan
    explicitly required it ("put the per-run summary somewhere tracked...
    the gitignored per-run sidecar cannot answer 'did the change help'
    across machines"), specifically to make cross-machine, cross-run
    comparison possible. A prior explicit operator instruction is not
    something a single reviewer's low-severity suggestion overrides.
- **Reconciliation:** the mini-plan's rejected alternative (a second phase
  marker) was never in question here — both reviews left it alone. What
  they rejected was infrastructure the plan added *beyond* what the
  brief's Option A described; adopting their simplification made Option A
  smaller than originally planned, not different in kind.

## External Code Review

### Round 1

- **Provider:** openrouter (deepseek + openai), Branch A, diffed against the
  merge-base with `origin/main` (`4ee334f0`), not `origin/main`'s moved tip
  (`61792495`) — per the standing "review the merge-base diff" rule, a moved
  main produces false-positive HIGH findings.
- **Verdicts:** deepseek=revise · openai=revise (no contradiction — both
  agree within one step).
- **Findings integrated:**
  - (openai, high) the persisted per-session summary carried an aggregate
    `unpriced_calls` count but no way to tell WHICH model needs a
    pricing-table entry — **accepted, scoped down**: a full per-call log was
    already rejected as disproportionate in two earlier external-review
    rounds (see Architecture Review above), so instead of reopening that,
    added one bounded, non-growing `unpriced_models` field (the sorted,
    deduplicated list of unpriced model ids) to the summary, `fold_into_event`,
    and the `_NO_DATA` default — closes the diagnosability gap without
    resurrecting the rejected per-call design.
  - (openai, medium) `compute_cost_usd` and `compute_summary`'s TTL-split
    detection used `cache_creation.get(key) or 0` truthiness, so an
    explicit-zero split (`{"ephemeral_5m_input_tokens": 0, ...}`) fell
    through to a stale/duplicated aggregate instead of winning as the
    already-documented contract promised — **accepted, fixed**: both sites
    now check key PRESENCE (`"key" in cache_creation`), not the value's
    truthiness.
  - (openai, medium) two distinct session ids could collapse onto the same
    on-disk file — `Path(session_id).name` strips directory components
    (blocks traversal) but not collision (`"other/victim"` and `"victim"`
    both resolve to `victim.json`), letting one session's write clobber
    another's — **accepted, fixed**: `context_cost_summary.session_summary_path`
    now validates against an allowlist regex and returns `None` (write/read
    skipped, never a derived basename) for anything that doesn't match; every
    writer and reader (the hook, the summary CLI, the statusline) calls this
    one function, never a local copy.
  - (openai, medium) `context_cost_readiness.py`'s own `MODEL_CONTEXT_WINDOWS.
    get(model)` had no date-suffix-stripping, so a real transcript's dated
    snapshot id (`claude-sonnet-5-20260612`) read back "not a known model" —
    **accepted, fixed**: `model_pricing.py` now exports `resolve_model_id`
    (the same exact-then-date-stripped policy `compute_cost_usd` already
    used internally) and the readiness check calls it instead of a bare
    dict lookup.
  - (deepseek, medium) a transiently-missing `transcript_path` was treated
    as "zero calls", and the hook would overwrite an already-recorded
    summary with that empty one on the very next `Stop` — **accepted,
    fixed**: the hook now checks the file's existence before calling
    `compute_summary` and skips the write entirely (preserving whatever was
    last durably recorded) when it's absent.
  - (deepseek, low) the missing-transcript regression test only asserted
    `rc == 0`, not that the summary file was left untouched — **accepted,
    fixed**: added a firing-then-remove-then-refire regression test that
    asserts byte-identical file contents across the skipped write.
- **Findings reviewed and not changed:**
  - (openai, low) `estimate_context_pressure.py`'s default (`--source
    toolcall`) output gained a new `"source": "toolcall"` key it didn't
    carry before this diff — **acknowledged, not changed**: the spec's own
    "default source unchanged" bullet is a behavioral claim (same
    thresholds, same `recommend_checkpoint` logic), not a byte-for-byte
    JSON-shape freeze; the one documented consumer (`/shipwright-build`'s
    checkpoint step) reads specific keys (`recommend_checkpoint`), not an
    exact key set, so the addition is inert in practice.
- **Self-discovered while fixing the above (not from either reviewer):**
  fixing the model-id resolver surfaced that a NEW test file added earlier
  this same round (`test_context_cost_hook_registration_additive.py`)
  inserted `shared/tests` onto `sys.path` at module level to reach a
  sibling test module — which shadowed `shared/scripts/tools` with the
  pre-existing, unrelated `shared/tests/tools/` test subpackage for every
  OTHER test file collected afterward in the same pytest session, breaking
  `test_context_cost_finalize.py`'s deferred `from tools.finalize_iterate
  import run` whenever collection order put the two files in that sequence
  (which alphabetical directory collection does). Fixed by switching that
  file to a package-relative import (`shared/tests/__init__.py` already
  makes it one) instead of a sys.path insertion — removes the collision at
  its source rather than working around it in every other file.
- **Test-file housekeeping:** two of the tests added to close these findings
  pushed `test_context_cost_core.py` and `test_track_context_cost.py` over
  the 300-line size guideline; both were split (fold/resolve-root tests →
  `test_context_cost_fold.py`, worktree end-to-end tests →
  `test_track_context_cost_worktree.py`) rather than left to grow, per the
  same extraction-over-baseline-bump approach used earlier this run for
  `context_cost_core.py` itself (see Design Notes).

### Round 2

Re-run against the Round-1 fixes, same merge-base diff basis.

- **Verdicts:** deepseek=revise · openai=revise (no contradiction). All six
  Round-1 findings confirmed closed by neither reviewer re-raising them.
- **Findings integrated:**
  - (openai, medium) `compute_cost_usd` rounded each call's cost to 6dp
    before returning it, and `compute_summary`'s per-phase bucket rounded
    again after every addition — a single cache-read token costs $0.0000003
    on Sonnet 5, below the 6dp threshold, so many small calls summed to
    permanently-lost cost even though their true total was well above it —
    **accepted, fixed**: `compute_cost_usd` now returns full, unrounded
    precision; `compute_summary` accumulates unrounded through the whole
    loop (both the session total and every phase bucket) and rounds exactly
    once, at the point each total is finalized for return.
  - (openai, medium) a Stop firing with neither a payload `session_id` nor
    `SHIPWRIGHT_SESSION_ID` set fell back to the literal string `"unknown"`,
    which would pool every such firing into one shared file — precisely the
    failure class this feature's whole payload-first design exists to route
    around (the documented 2026-05-29 `bloat_gate_on_stop.py` incident) —
    **accepted, fixed**: `resolve_session_id` now returns `None` instead of
    a placeholder string when neither source has a real id; the hook checks
    for this explicitly and skips the write (every downstream reader
    already degrades a falsy/non-string session id to its no-data default,
    via the Round-1 `session_summary_path` validator). Fixed the identical
    pattern in `estimate_context_pressure.py`'s own separate `"unknown"`
    fallback for consistency, though that process class's env var is
    documented as reliable and this branch is not known to fire in
    production for it.
  - (openai, medium) a transcript record with a wrong-TYPE (not merely
    missing) field — a non-numeric token count, or an unhashable `model`/
    `requestId` — raised out of the entire `compute_summary` loop, silently
    discarding every OTHER call in the same transcript, not just the
    malformed one — **accepted, fixed**: `requestId`/`model` are now
    validated as non-empty strings (dropping the whole record as
    `skipped_malformed`, matching the existing missing-field precedent);
    every token-count field goes through a `_num()` coercion (malformed →
    0 for that one field, call still counted) in both `context_cost_core`
    and, for defense-in-depth on the public API, `model_pricing.
    compute_cost_usd` independently.
- **Findings integrated (documentation only):**
  - (deepseek, low) `docs/hooks-and-pipeline.md`'s Stop-hook row still said
    the persisted summary "has ... no `unpriced_model` field" — stale
    against Round 1's own `unpriced_models` addition — **accepted, fixed**:
    description corrected to name the actual field.
- **Verdict:** ship. Every finding from both rounds is closed; no third
  round was run, since re-running further external review after two
  substantive rounds each of plan/architecture/code review on this feature
  would be diminishing-returns process, not a materially different check.

## Verification (medium+)

- **Surface:** cli
- **Runner command:** `uv run shared/scripts/hooks/track_context_cost.py`
  against a fixture transcript, followed by
  `uv run shared/scripts/tools/context_cost_summary.py show --project-root . --session-id <fixture-session-id>`
- **Evidence path:** `.shipwright/compliance/context-cost/<session_id>.json`
  (produced) + the show-command's stdout captured at F0.5
- **Justification (only if surface=none):** n/a
