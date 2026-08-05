# Iterate Timings — hierarchical lifecycle spans (measurement only)

Separate, richer sibling of [phase-timing](phase-timing.md) (the 5-group
`phase_timings` system, which this does NOT replace). Where `phase_timings`
records five flat boundary marks, this records a **tree** of named spans
across the whole iterate lifecycle — discovery through delivery — and
distinguishes **producer-owned** spans (a real process brackets its own
start/end; no agent action needed) from **agent-emitted** marks (no process
owns the boundary, so the session marks it as it crosses).

**Measurement only.** This system never changes a verdict, gate, retry
decision, review cascade, CI requirement, or delivery outcome. A missing or
interrupted mark never blocks an iterate — it shows up as `incomplete` /
`unattributed` in the report, never as zero duration.

## Why a second system, and why most of the burden moves off the agent

`phase_timings` asks the agent to remember five `mark` calls across an entire
session; measured history shows 4 of 5 recent runs recorded exactly ONE of
them. That is not a bug to fix by asking harder — it is the design constraint.
This system fixes it structurally: **every span that has a real process
boundary is now stamped by that process itself**, not by an agent
remembering a shell command. Only the handful of boundaries with no owning
process (entering Build, entering Self-Review, a reviewer dispatch, …) stay
agent-emitted, and their absence is reported honestly, never hidden.

## The catalog

7 top-level groups (parent `none`):

`discovery_diagnosis · planning · implementation · verification · review · finalization · delivery`

All are agent-emitted EXCEPT `delivery`, which `deliver_pr.py::deliver()`
self-records (producer) alongside its `delivery_wait`/`ci_wait` children when
`record_timing=True` — no agent mark needed. A redundant agent `start
delivery` is harmless (multiple top-level instances of the same name are
valid; the tightest-fitting one wins for attaching children).

14 nested spans (parent in parentheses; a name may be valid under more than
one parent):

| Span | Parent(s) | Owner |
|---|---|---|
| `focused_tests` | `implementation` | agent |
| `pre_f0_validation` | `verification` | **producer** — `check_iterate_isolation.py --stage f0` self-instruments |
| `f0_queue` | `verification` | **producer** — `run_test_suite.py` (host-lease `waited_seconds`) |
| `canonical_f0_active` | `verification` | **producer** — `run_test_suite.py` (`SuiteResult.duration`) |
| `self_review` | `review` | agent |
| `spec_review` | `review` | agent (Task-tool subagent spawn — no OS process to instrument) |
| `code_review` | `review` | agent |
| `doubt_review` | `review` | agent |
| `external_review` | `planning`, `review` | **producer** — `external_review.py` self-instruments when `--run-id` is passed |
| `reviewer_wait` | `planning`, `review` | agent (internal subagent dispatch → receipt) |
| `remediation` | `review` | agent |
| `delivery_wait` | `delivery` | **producer** — `deliver_pr.py::deliver()` when `record_timing=True` (the real CLI path only) |
| `ci_wait` | `delivery`, `delivery_wait` | **producer** — same call, wraps the `watch()`/`self_merge()` sub-call |
| `post_ci_remediation` | `delivery` | agent (diagnose+fix+repush — no process owns this) |

## Producer-owned vs agent-emitted — the actual split, verified against code

Verified against the real F0 runner, `external_review.py`, and the F11
delivery ladder (not assumed): a producer boundary exists wherever a single
OS process's own lifetime already IS the span. That is true for the F0
leak-guard, the F0 host-lease acquire/run boundary, the external-review LLM
call, and the delivery ladder's arm/watch/merge sequence — none of those
needed a NEW mechanism, only persisting timestamps those processes already
compute (e.g. `LeaseGrant.waited_seconds`) and today discard.

It is **not** true for a Task-tool subagent spawn (`spec-reviewer`,
`code-reviewer`, `doubt-reviewer`) — that dispatch happens inside Claude
Code's own orchestration, not a `uv run` subprocess this repo's scripts can
hook into. Those stay agent-emitted; their absence is reported as
`unattributed` with a reason, never silently omitted or zeroed.

**Contract for a producer-owned span's containing parent:** a nested
producer span is only attachable if a containing top-level instance exists
in the sidecar. `deliver_pr.py` self-records `delivery` (top-level) alongside
`delivery_wait`/`ci_wait` for exactly this reason — an earlier design left
`delivery` agent-only and required the SKILL to mark `start delivery` before
invoking `deliver_pr.py`, a fragile cross-component contract an external plan
review flagged (a missed mark silently dropped `delivery_wait`/`ci_wait` as
"no containing parent" — per-entry, not fatal to the rest of the run, but
still a real gap). Prefer the producer owning its own root wherever it can.

## Agent-emitted marks — where to call them

Best-effort — suffix `|| true` so a transient mark failure never blocks the
iterate:

```bash
uv run "{shared_root}/scripts/tools/iterate_timing.py" start <name> \
  --parent <parent|none> --project-root "{project_root}" --run-id "{run_id}" || true
uv run "{shared_root}/scripts/tools/iterate_timing.py" end <name> \
  --parent <parent|none> --project-root "{project_root}" --run-id "{run_id}" \
  [--outcome completed|incomplete|cancelled] [--extra-json '{...}'] || true
```

| Call | When |
|---|---|
| `start discovery_diagnosis --parent none` | BUG intent, entering F-debug's Read-Error phase |
| `end discovery_diagnosis` / `start planning --parent none` | Intent classified non-BUG, or F-debug root-cause found |
| `end planning` / `start implementation --parent none` | Step 6 entry (Build) — same anchor as the existing `mark build` |
| `end implementation` / `start review --parent none` + `start self_review --parent review` | Step 7 entry (Self-Review) — same anchor as `mark review` |
| `end self_review` / `start spec_review --parent review` … `end spec_review` / `start code_review …` / `start doubt_review …` | Step 8's cascade, bracketing each stage's Agent-tool call |
| `end review` / `start verification --parent none` | F0 entry — same anchor as `mark test`. The three F0 sub-spans self-instrument; do not mark them by hand. |
| `end verification` / `start finalization --parent none` | F1 entry — same anchor as `mark finalize` |
| `end finalization` | F11 entry — `deliver_pr.py` self-records `delivery`/`delivery_wait`/`ci_wait`; no `start delivery` mark needed |
| `start post_ci_remediation --parent delivery` / `end post_ci_remediation` | Only on a `checks_failed` verdict — bracket the diagnose→fix→re-push work |

## Storage contract

- Sidecar: `.shipwright/agent_docs/iterates/<run_id>.iterate_timings.jsonl` —
  GITIGNORED, resumable (append-only; a resumed session sees everything an
  earlier one wrote), sibling of `<run_id>.phase_timings.jsonl`. Two line
  shapes: `{"event":"start"|"end", ...}` (agent, paired across turns) and
  `{"event":"span", ...}` (producer, one atomic record).
- Fold: `finalize_iterate.py` (F5b) calls
  `lib.iterate_timings_normalize.fold_into_event`, directly beside the
  existing `phase_timings` fold. Additive — never overwrites a pre-existing
  `iterate_timings` field, never blocks finalize on a fold failure.
- Validation: **per-entry**, not all-or-nothing. A malformed span (unknown
  name, invalid parent, negative duration, impossible ordering vs. its
  claimed parent, an unbounded/unknown `extra` key) is dropped with a reason
  logged to stderr; the rest of the run's spans still persist. This is the
  deliberate fix for `phase_timings`' all-or-nothing validation, which meant
  one bad mark could zero an entire run's data.
- Durable field: `work_completed.iterate_timings` — a flat list of
  `{name, parent, source, outcome, start_utc, end_utc, duration_ms,
  exclusive_ms, attempt, extra}`. `exclusive_ms` is inclusive duration minus
  the **union** (not sum) of contained children's intervals — two overlapping
  children (a parallel review pass, say) would double-count their overlap if
  simply summed, silently under-reporting (or zero-clamping) the parent's own
  exclusive time; the union is computed exactly once regardless of how many
  children cover it (external plan review). `source` ∈
  `producer | agent | derived`. `outcome` ∈
  `completed | incomplete | cancelled | unavailable`.
- **Known scope boundary — the `finalization`/`delivery` tail and the durable
  event.** F6 (commit) stages the F5b-recorded `work_completed` event and F11
  pushes that commit; CI/delivery wait time is fundamentally unknown until
  AFTER the push, so it cannot be embedded in the SAME immutable,
  already-pushed commit without either a follow-up commit racing an async
  host auto-merge (rung 2 — unsafe, GitHub can merge before any amendment
  lands) or a new post-merge write mechanism (out of scope for a
  measurement-only card — no new CI jobs, no policy decisions). Traced
  precisely (doubt review): this is not limited to the 3 nested
  `ci_wait`/`delivery_wait`/`post_ci_remediation` spans — the entire
  top-level `delivery` group is unreachable too (it only self-records from
  the real F11 CLI invocation, which runs after F5b), and `finalization`'s
  own duration is equally unreachable (its `end` mark sits at F11 entry per
  the table above, so it is always still-open when F5b folds). In every
  worktree-flow run, structurally, not occasionally. `FOLD_TIME_CAPTURABLE_SPANS`
  in `iterate_timings.py` names the 5 groups that genuinely CAN close by
  fold time (`discovery_diagnosis`, `planning`, `implementation`,
  `verification`, `review`) — coverage/`degraded` and the report's "Total
  wall-clock" are measured against that set, not all 7, so a run where those
  5 close cleanly reads as complete rather than permanently DEGRADED.
  `finalization`/`delivery` still render per-run when present (start-only for
  `finalization`, absent entirely for `delivery`) — they are simply not
  penalized for an incompleteness the architecture guarantees. `ci_wait`/
  `delivery_wait`/`post_ci_remediation` ARE recorded to the sidecar (useful
  for diagnosing a stuck F11 in the current run) but do not reach the durable
  event or the cross-run rolling report. Named here deliberately rather than
  silently shipped as if solved — durable delivery-phase attribution is the
  natural, cleanly-scoped follow-up once the operator has reviewed a few
  instrumented runs.
- Cross-process timestamps rely on system clock accuracy — spans are stamped
  with `datetime.now(timezone.utc)`, not a shared monotonic source, so minor
  drift between producer processes on the same machine could shift a
  parent-child boundary by a few milliseconds. Immaterial for this system's
  purpose (measurement, not causal ordering); noted as a limitation, not
  something the fold/normalize layer attempts to correct.
- Report: `.shipwright/compliance/performance/iterate-throughput.md`,
  regenerated by `iterate_throughput_report.py` at F5b (best-effort,
  in-process). Reproducible entirely from `shipwright_events.jsonl` — never a
  second metrics store, never loaded as agent startup context.
- Retention: the sidecar itself has no retention policy (one file per run,
  gitignored, harmless if it accumulates locally). The report's rolling
  window is the last 10 instrumented `work_completed` events, same window as
  the existing `event_context_metrics` precedent.

## Extending the catalog

`extra` is a closed vocabulary (`shared/scripts/lib/iterate_timings.py`
`EXTRA_FIELD_TYPES`) — bounded, scalar fields only (`waited_seconds`,
`provider`, `rung`, `polls`, `timed_out`, …). Never add a prompt, finding,
source excerpt, console log, or test output to it; that is the hard NEVER
this card exists to enforce. Add a new span name or parent relationship in
`shared/scripts/lib/iterate_timings.py::SPAN_PARENTS` and update the table
above in the same diff.
