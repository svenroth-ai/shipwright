# Measure real per-token cost from the transcript instead of counting tool calls

## Context

`estimate_context_pressure.py` has shipped one proxy since it was built:
tool-call count against two hardcoded thresholds. Two prior cost
investigations in this monorepo both trusted that proxy and both drew a
wrong conclusion from it, because tool-call count cannot see cost broken
down by pipeline phase, and a call-heavy phase does not have to be a
token-heavy one. The assistant's own transcript already carries the real
per-token usage on every `assistant` record — dedup by `requestId`, since
one exchange is written as several transcript lines that all share one
request id.

## Decision

A new additive `Stop` hook, `shared/scripts/hooks/track_context_cost.py`
(registered on `shipwright-build` only), recomputes the session's ENTIRE
transcript on every firing and overwrites one JSON file per session,
`.shipwright/compliance/context-cost/<session_id>.json`. No incremental
cache: sessions are small (median ~276 calls) and cheap to re-read in
full; full-recompute-and-overwrite eliminates concurrent-`Stop`-race and
stale-cache classes by construction — both external-review rounds on this
feature converged on this over a standing append-only cache design.

Each call is priced per-token-type (`shared/scripts/lib/model_pricing.py`)
including the cache-read/cache-write TTL split, never blended into the
input rate — a blended rate previously put cost estimates off by roughly
an order of magnitude. An unrecognized model id NEVER falls back to
another model's price: `compute_cost_usd` returns `(None, True)`, rolled
into `unpriced_calls`/`unpriced_models`, never into `cost_usd`, and the
aggregate is flagged `cost_complete: false`. Session id is resolved from
the hook's stdin payload first, `SHIPWRIGHT_SESSION_ID` only as fallback —
a bare env-var fallback would reintroduce the exact cross-session file
collision (`"unknown".json` pooling) an earlier incident in this same
hook class already required fixing once. `estimate_context_pressure.py`
gains an opt-in `--source context-cost` (default stays `toolcall`), and
the summary folds into the run's tracked `work_completed` event at F5b.

## Consequences

A session gets a real, priced cost figure broken down by phase, available
while the session is still running (via `context_cost_summary.py show`
and an operator-wired statusline), without a second aggregation engine —
the Stop hook, the summary/statusline readers, and the F5b fold all call
the same `context_cost_core.compute_summary`. The tracked
`work_completed.context_cost` figure is bounded through the last `Stop`
firing before F6, so it is a floor on true session cost, never the whole
session (F6-F12 are not measured) — documented via a `measured_through`
stamp rather than silently treated as a whole-session number. A new
`context_cost_readiness.py` check reports `autoCompactWindow`-vs-context-
window and effort-level findings in the same shape `verify_local.py`
already uses.

## Rationale

Two full rounds of external code review (openai + deepseek) ran against
this feature after the initial build, converging on nine total findings,
all fixed or explicitly declined with a documented reason (a `"source"`
key addition to `estimate_context_pressure.py`'s default output, verified
to have no consumer reading an exact key set). Round 1 fixed: the missing
automatic-wiring gap, a TTL-split truthiness bug (an explicit-zero split
must still beat a stale nonzero aggregate), a session-id path-traversal
AND collision gap (an allowlist regex, not just `Path(...).name`), a
missing-transcript-on-a-later-firing gap that could silently wipe a prior
valid summary, and the `unpriced_models` diagnostic field (a bare count
could not say WHICH model needs a pricing-table entry). Round 2 fixed: a
precision-loss bug from rounding each call to 6dp before summing (a single
Sonnet-5 cache-read token costs $0.0000003, below that threshold, so many
small real calls silently zeroed out before ever reaching a total); the
`"unknown"` session-id fallback pooling bug described above; and a
malformed-TYPE record (a string `input_tokens`, an unhashable `model`)
that used to raise out of the ENTIRE transcript loop, discarding every
OTHER call in the same file rather than degrading just the one malformed
field/record.

## Rejected alternatives

A standing incremental append-only cache was proposed and rejected twice
by external review as disproportionate for a transcript this small and
this cheap to re-read whole — the failure classes it would need to defend
against (concurrent-writer races, stale entries, cache/source drift) are
eliminated by construction under full recompute instead. A persisted
per-call log (one row per API call, forever) was rejected as
disproportionate given the transcript itself remains the source of truth
for anything finer-grained than the bounded `unpriced_models` diagnostic;
Round 1's HIGH finding asking for exactly this was resolved by adding that
one bounded, non-growing field rather than reopening the already-settled
per-call-log rejection. A blended "total tokens × input rate" pricing
model was rejected outright: cache-read tokens measured at ~82% of an
actual bill, so blending them into the input rate overstates real cost by
roughly an order of magnitude.
