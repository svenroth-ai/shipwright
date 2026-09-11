# ADR: Bloat exception — grow `shared/scripts/triage.py` to 909 lines (extends ADR-121)

- **Status:** accepted
- **Date:** 2026-09-10
- **Re-Review-Date:** 2026-12-10
- **Incident Reference:** iterate `iterate-2026-09-10-triage-cross-tree-precedence`,
  card `trg-74ef24ce` (the resurrected-dismissed-card defect being fixed).

## Context

`shared/scripts/triage.py` is already a `state="exception"` file under
ADR-121 (baseline `current: 893`, itself raised from ADR-100's 837 and an
earlier grandfathered 592) — a deep module by design: the interface is
`append_triage_item`/`mark_status`/`read_all_items` plus outbox routing,
behind which sit cross-process locking, tolerant JSONL parsing, and the
two-file union resolution `read_all_items` performs. This iterate adds a
sixth resolution rule to that same union reader — a foreign (sibling-
worktree) `status` event applies only when this tree's own tracked+outbox
union has not already decided that id — fixing a measured defect where a
stale sibling reopen could resurrect an already-dismissed card. Splitting
`triage.py` remains refused for the same reason ADR-100/121 already argued:
the lock, the path helpers, the append writer and the union reader share
invariants that only hold when read and modified together, and this change
touches exactly that shared reader.

The +16 lines (893 → 909, after a code-review pass folded the local/foreign
split back into the pre-fix drop-filter shape and deleted the now-dead
`_iter_raw_lines`) are: the `local_status_ids` gate (with its `newStatus in
STATUSES` validity filter and `isinstance(str)` guard — the guard added in
response to an external-review-found crash bug during this same iterate, not
scope creep), the foreign-side drop-filter, and the docstring update the
Test-Update-Klausel requires for the corrected precedence rule. No responsibility was added that
this fix does not need: no new file, no new public entry point, no policy
moved into `triage.py` that could instead live in `lib.triage_cross_tree`
(the rejected-alternative section of this iterate's mini-plan argues that
explicitly — filtering at the source would invert the module boundary
`lib/triage_cross_tree.py` already documents).

## Decision

Bump `shared/scripts/triage.py`'s `shipwright_bloat_baseline.json` entry
`current` from 893 to 909, keeping `state="exception"` and `adr="ADR-121"` —
this growth extends the same deep-module argument ADR-121 already makes for
this file, the same way ADR-121 is already cited for two other files' later
bumps in the same baseline (550 and 932 lines) rather than each minting its
own number.

## Consequences

The file stays exempt from the anti-ratchet gate at 909 lines. A future
iterate that extends `triage.py` again re-trips the gate and must justify
that growth fresh — this ADR does not pre-authorize further growth. The
Re-Review-Date carries ADR-121's own open question forward: whether the
now six-rule resolution surface in `read_all_items` still argues for staying
in one file, or has grown enough to warrant extracting the precedence/
resolution logic (append + status + amend + expiry + cross-tree fold +
this iterate's local-wins rule) into its own narrow module the way
`triage_defer.py` and `triage_contract.py` were already extracted.

## Rejected alternatives

**Split `read_all_items`'s resolution logic out of `triage.py` now** —
rejected as out-of-scope churn for a targeted bug fix already through two
external review rounds (plan-stage and code-stage) plus an internal
opus-plan-reviewer pass; a real extraction needs its own iterate to decide
where the five pre-existing resolution rules (append/status/amend/expiry/
cross-tree) plus this one's new precedence rule would live, and to migrate
their tests without churning unrelated call sites.

**Trim further to close the remaining +16 and stay under 893** — a code-review
pass already recovered +20 of the initial +36 (folding the local/foreign split
into the pre-fix drop-filter shape, deleting the now-dead `_iter_raw_lines`,
consolidating three copies of the precedence-rule explanation into one).
Trimming the remaining +16 further would mean cutting `local_status_ids`'s own
validity filter, the crash-guard `isinstance` check, or the precedence rule's
rationale from `read_all_items`'s docstring — the one place ADR-121 already
establishes as this module's canonical home for resolution rules — reproducing
exactly the drift ADR-121 argues against.
