# ADR-100: Bloat exception — `shared/scripts/triage.py` raised to 719-LOC

- **Status:** accepted
- **Date:** 2026-06-08
- **Re-Review-Date:** 2026-09-08
- **Incident Reference:** iterate `iterate-2026-06-08-outbox-delivery-d1`
  (campaign `2026-06-08-triage-outbox-delivery`, sub-iterate D1). The
  per-tree gitignored outbox + union reader pushed `triage.py` from its
  grandfathered `current` of 592 to a measured 719.

## Context

`shared/scripts/triage.py` is the Single Source of Truth for the triage
intake store (append-only JSONL under `.shipwright/`). It was already
grandfathered at 592 LOC (`state: grandfathered`, no ADR) — a pre-existing
crossing of the 300-line limit recorded, not introduced, by this iterate.

D1 added a genuinely new concern: a per-tree GITIGNORED outbox buffer
(`triage.outbox.jsonl`) that idle-main background producers write instead
of the tracked log (killing main-tree drift), plus a union reader so Python
consumers still see background findings immediately. The new code:
`OUTBOX_FILE`/`_outbox_path`, `should_route_to_outbox` (branch-based router),
`_append_line` (shared locked-append), the `_iter_raw_lines_at` / union
`_iter_raw_lines` split, `to_outbox` params on the 3 write APIs, a union-aware
`mark_status`, and a two-pass + ts-primary `read_all_items` resolver. The
resolver's invariant docstrings are load-bearing — two distinct cross-file
precedence bugs (found by external review + empirical probes) are documented
inline precisely so a future editor does not regress them.

## Ousterhout Argument

`triage.py` is a **deep module**: the public interface is narrow —
`append_triage_item`, `append_triage_item_idempotent`, `mark_status`,
`read_all_items`, plus the `OUTBOX_FILE`/`should_route_to_outbox` routing
surface. Behind that small interface sits substantial, encapsulated
behaviour: cross-platform file locking, header bootstrap, tolerant
JSONL parsing, idempotent dedup under lock, last-status-wins resolution,
and now two-file union resolution with chronological ordering. Splitting
would expose internals that MUST stay co-located: the lock, the path
helpers, the append writer, and the union reader all share invariants
(one canonical lock; appends-before-statuses; tracked-vs-outbox routing)
that only hold when they are read and modified together. A split would
turn one cohesive boundary into two files that must be kept manually in
lock-step — strictly worse for the AI-edit-reliability concern the limit
exists to protect.

## YAGNI Check

Walked each responsibility added by D1:
- Outbox path + constant — needed today (the buffer must exist).
- `should_route_to_outbox` — needed today (the 3 producers call it).
- `_append_line` — needed today; it also REMOVES duplication (three call
  sites previously inlined `open/write/flush/fsync`). Net simplification.
- Two-pass + ts-primary resolver — needed today; without it the union
  silently drops dismiss/promote across the split (proven by probe).
- `_iter_raw_lines_at` — needed today; GC/reconcile require a tracked-only
  reader to avoid folding the outbox into the tracked log.
No speculative scope was added. A dead single-use helper (`_write_path`)
that crept in during the build was DELETED before this ADR (Dead-Code
Artifact Check) — the exception covers only code that cannot be removed.

## Chesterton-Fence Check

The 592 fence is the prior grandfathered size; git history shows the file
has accreted one cohesive concern at a time (idempotent append, launch
payload, FR/suite/event refs, GC interplay) — each an extension of the same
SSoT, never a candidate for extraction. The fence stands for a real reason:
this is the one place every triage producer and consumer agrees on the wire
format and resolution rules. D1 extends the same fence (outbox is another
file of the SAME format, resolved by the SAME reader). Tearing it down
(splitting) would breach the very co-location the fence protects.

## Decision

Grant `shared/scripts/triage.py` a bloat exception with `current: 719`,
`state: exception`, `adr: ADR-100`. Retirement plan: when the triage GC /
sweep machinery (campaign D2) and the read-resolution rules stabilize, a
follow-up iterate may extract the pure resolution logic
(`read_all_items` + `_iter_raw_lines*`) into a sibling `triage_resolve.py`
behind the same interface — re-evaluated at the Re-Review-Date.

## Consequences

- The anti-ratchet pre-commit hook + Group H audit now measure `triage.py`
  against 719, not 592. A future edit that grows it further needs its own
  deliberate bump.
- No downstream consumer changes — the interface is unchanged; only the
  baseline ceiling moved.
- Cost if it holds past Re-Review-Date: the file stays a single ~720-LOC
  module. Acceptable: it is coherent and deep; the alternative (a forced
  split) costs more in cross-file invariant drift risk.

## Rejected alternatives

- **Leave at 592 and split now.** Rejected: D1's new code is inseparable
  from the existing lock/path/reader machinery (see Ousterhout); a split
  this iterate would create two files that must move in lock-step, raising
  (not lowering) edit-error risk — the opposite of the limit's intent.
- **Shallow refactor to shave lines.** Rejected: the residual growth is
  load-bearing code + invariant docs that external review specifically
  validated; cosmetic shaving would delete the regression-guard rationale
  for two probe-found bugs.
- **Drop the feature.** Rejected: the outbox reroute is the campaign's
  core deliverable (kills main-tree triage drift at its source).

---

## External Sources Acknowledged

This ADR's YAGNI Check + Chesterton-Fence Check headings are adapted from:

- obra/superpowers, skill `writing-plans` —
  https://github.com/obra/superpowers — MIT © Jesse Vincent
- addyosmani/agent-skills, skill `code-simplification` —
  https://github.com/addyosmani/agent-skills — MIT © Addy Osmani

The Incident-Reference field follows the **pattern** of the per-decision
incident-reference convention in `multica-ai/multica` `CLAUDE.md`
(Apache-2.0 modified-with-hosting-restriction — patterns reusable, text
not copied).
