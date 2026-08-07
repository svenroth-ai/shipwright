# Architecture Brief: context-cost-meter

## The problem

Two prior investigations tried to explain what this framework's sessions
cost and both drew a wrong conclusion, because nothing in the project
measures actual dollar cost per call — only a raw tool-call counter exists,
and it cannot be broken down by which pipeline phase spent it. Operators
cannot see cost pressure building while a session runs, only estimate it
afterward, badly.

## What already exists here

- `.shipwright/toolcall_count` + `estimate_context_pressure.py` — counts
  tool invocations (not API cost) against two fixed thresholds, to warn
  when a session may be running out of working context.
- `iterate_phase_groups` — a sidecar that already timestamps the five
  pipeline-phase boundaries (`scope build review test finalize`) for
  wall-clock duration reporting.
- `verify_local.py` — a local pre-push readiness report in a fixed
  checks-list shape.

## What would newly, permanently exist

A `Stop`-hook-driven measurement of actual API cost, read from the
assistant's own transcript and priced from a hardcoded rate table, written
incrementally to a per-run cache and folded into the project's tracked
event log at the end of each run. From then on, every session carries a
real cost figure, split by phase, that the project's own history and
tooling can be compared against over time.

## Options on the table

- **A:** Measure cost from the transcript's own usage records (request-id
  deduplicated), tag each call by the already-existing phase-boundary
  marks, and record it — no new marking mechanism.
- **B:** Estimate cost from the existing tool-call counter using an average
  $/call figure derived from past sessions, without reading transcripts.
- **C:** Do nothing further — keep relying on ad-hoc, after-the-fact
  measurement scripts run by hand when someone asks "what did that cost".

## Constraints that are not negotiable

- A plugin cannot change the user's Claude Code settings (e.g.
  `autoCompactWindow`) — it can only read and report on them.
- The existing tool-call-count pressure warning must keep working exactly
  as it does today; nothing may remove or silently change its behavior in
  this change.
