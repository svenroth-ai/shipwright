# Synthesize a missing ancestor for iterate_timings instead of orphaning its children

## Context

P1.17 (#551, merged 2026-08-05 05:29) shipped self-instrumenting producer
spans for the `iterate_timings` measurement system (F0's queue/active
durations, `external_review` calls, the delivery ladder). Eight real runs
later, ZERO `work_completed` events carried `iterate_timings` data.

Root cause: every producer-owned span declares a parent among the 7
top-level lifecycle groups (`discovery_diagnosis`, `planning`,
`implementation`, `verification`, `review`, `finalization`, `delivery`).
Six of those seven are agent-emitted — the SKILL is supposed to call
`iterate_timing.py start/end` at phase boundaries — and in practice the
agent essentially never does. `_attach_parents` (`iterate_timings_normalize.py`)
rejected every producer child that named an unmarked parent as "no
containing parent instance," so the fold at F5b had nothing valid to
persist on any of the 8 runs measured 2026-08-05. This is the same failure
class `phase_timings` already showed (4 of 5 recent runs recorded exactly
one of its five marks), one layer up: the producers stopped depending on
the agent to remember a mark, but they were still hung off scaffolding —
the 6 agent-emitted top-level parents — that only an agent emits.

Verified empirically against the three real `.iterate_timings.jsonl`
sidecars still on disk (`bloat-baseline-vendored-hook`, `semver-prerelease-sort`)
before writing any fix: `verification`/`planning`/`review` never appear as
top-level records in either file; every F0 and `external_review` producer
span is consequently orphaned.

## Decision

`_attach_parents` now distinguishes two failure shapes for a nested span
with no valid containing parent, instead of one:

1. An instance of the child's own **declared** parent name exists
   somewhere in the run but doesn't temporally contain it — the existing
   "impossible ordering" guard, still rejected, never synthesized around.
2. No instance of the declared name exists anywhere — the missing ancestor
   is **materialized** from the envelope (earliest start, latest end) of
   the children that name it, in rounds (bounded by the span catalog's
   size) so a synthesized ancestor that is itself nested recurses
   correctly (e.g. a derived `delivery_wait` still needing `delivery`).

A synthesized span carries `source: "derived"` (the third value in the
`SOURCES` vocabulary, present in the original card but never produced
until this fix) and `outcome: "incomplete"` whenever a referencing child is
still open. A real agent/producer record for the declared name, whenever
one exists — even an unclosed agent mark — always wins; synthesis only
fires when the containment search finds zero named candidates for that
specific declared name (not the union of every name the span type would
accept — a real spec-review round found and fixed a gap where a
real-but-irrelevant record under a sibling allowed name could silently
suppress synthesis for multi-parent-name spans like `external_review`).
The reporting layer (`iterate_throughput_stats.py`/`iterate_throughput_render.py`)
shows a derived span's real duration but excludes it from `coverage_top_level`
(coverage means "the agent/producer actually marked this boundary"), and
labels it explicitly in the rendered table rather than showing it
identically to a measured span.

A doubt-review pass also found and fixed a genuine precedence bug
predating this change: `_SOURCE_RANK` ranked `derived` above `agent`,
contradicting the requirement that a real agent-emitted mark must always
win — reordered to `producer=0, agent=1, derived=2`, pinned by a new
direct test independent of `_attach_parents`.

## Consequences

`work_completed.iterate_timings` and the derived
`.shipwright/compliance/performance/iterate-throughput.md` report now
populate on every run, even when the agent emits zero top-level marks —
verified against both real production sidecars, which normalize from 0
persisted entries (today) to 14 and 9 respectively with zero rejections.
Two structural edge cases are accepted as documented limitations rather
than engineered around (see `iterate-timings.md`'s "Synthesizing a missing
ancestor" section): temporally-disjoint episodes sharing one missing
declared parent merge into a single envelope with a misleading total
duration (mitigated by the existing `exclusive_ms` figure surfacing the
gap, and not observed in either real production run); and round-batched
synthesis can, in one narrow write-failure scenario on the `delivery`
chain, fall back to the pre-fix rejection behavior rather than widening
correctly. Neither corrupts data or gates a verdict — this remains a
measurement-only system.

## Rationale

The fix direction was specified explicitly rather than left open: "do not
solve it by asking agents to emit the parents... synthesize a missing
ancestor from its children... mark it derived/incomplete." Implementing
temporal-cluster-splitting for the disjoint-episode edge case, or a
two-pass widening algorithm for the narrow round-ordering case, would have
gone beyond the literal "envelope: earliest start, latest end" ask for
edge cases neither observed in real data nor reachable via the real CLI
path — added complexity and risk without a demonstrated need, against a
system whose own design principle is "measurement only... a missing mark
never blocks an iterate."

## Rejected alternatives

Asking agents to reliably emit all 6 top-level marks was rejected outright
by the fix direction itself, and independently by measured history — this
is the identical dependency `phase_timings` already proved doesn't hold in
practice. Engineering around both doubt-review edge cases (temporal
clustering, two-pass ancestor widening) was considered and rejected as
scope creep beyond the specified fix, given neither is observed in real
data and both degrade honestly (a visible exclusive-time gap; a fallback
to pre-fix rejection) rather than silently.
