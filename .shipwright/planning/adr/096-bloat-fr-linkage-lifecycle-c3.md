# ADR-096: Bloat exception — FR-linkage lifecycle files raised for C3 (finalize FR-gate + D3 same-event)

- **Status:** accepted
- **Date:** 2026-06-05
- **Re-Review-Date:** 2026-09-05 _(retire when `finalize_iterate` / the
  Group-D audit + their suites are split per-concern — candidate for the B/C
  bloat-cleanup campaigns; ADR-095 set the same horizon for the sibling audit
  files)._
- **Incident Reference:** campaign `2026-06-02-compliance-detective-realign`
  (anchor triage `trg-5eb9b125`), sub-iterate **C3** (FR-gate finalize-bypass
  closure + D3 same-event delivery semantics). First crossing surfaced when the
  write-gate + the D3 fix + their mandated regression tests pushed four
  already-oversize files past their baseline.

## Context

ADR-095 explicitly deferred C3/C4's files ("the C3/C4 sub-iterates … will touch
`group_d.py` / `record_event.py` / `finalize_iterate.py` — out of scope here").
C3 closes the FR-gate bypass on the worktree finalize write-path
(`finalize_iterate._record_event` now runs `record_event._fr_or_change_type_gate_error`
before `append_event`, fail-closed) and relaxes Group-D D3 to count a same-event
`new_frs`+`affected_frs` delivery. The growth, per file:

Source:
- `finalize_iterate.py` 475 → 532 (+57): a `FinalizeGateError` type, the gate
  call sited AFTER the idempotency early-return and BEFORE `append_event`, the
  except-ordering that lets it propagate (not swallowed by the best-effort
  handler), the CLI exit-1 handler, and the `run()` fail-closed contract note.
  `record_event.py` absorbed the single-source-of-truth docstring correction
  **net-neutral** (797 → 797) — the gate logic was reused, not re-implemented.
- `group_d.py` 457 → 465 (+8): the D3 delivery test changed `>` to `>=` with a
  six-line "why" comment (the `FR-01.33` same-event false-positive) + a
  module-docstring correction.

Tests:
- `test_finalize_iterate.py` 306 → 464 (+158): seven new cases (reject-no-FR,
  allow-`affected_frs`, allow-`change_type`-pair, reject-malformed-`change_type`,
  idempotency-not-re-gated, CLI-exit-1, regen-aborted-on-rejection) + the ~12
  pre-existing dashboard/handoff/idempotency cases updated to supply the
  now-required classification (a shared constant + a small import helper), not
  weakened.
- `test_audit_groups_a_d.py` 748 → 789 (+41): two D3 cases (same-event delivered
  → pass; re-promised-never-affected → still flagged) + a module-docstring
  correction.

## Ousterhout Argument

Each file is a **deep module**: `finalize_iterate.py` exposes one `run()`
orchestrating the iterate's deterministic finalization (event → compliance →
dashboard → handoff → triage) behind a narrow CLI; `group_d.py` exposes one
`run()` over a cohesive group of event×spec detective checks (D1–D5). The gate
belongs INSIDE `_record_event` (the single write chokepoint) — extracting it to
dodge +57 would scatter the write-path's fail-closed contract away from the
writer it guards. The test files are the matching suites with shared fixtures;
splitting them to shave a +41/+158 increment would fragment the per-behaviour
cases the suite exists to hold together.

## YAGNI Check

Every added line backs a behaviour shipped today: the gate prevents the exact
FR-less event class (`evt-83b9b73f`) that D5 historically caught only after the
fact; the D3 relaxation clears the `FR-01.33` perpetual false-positive. The
tests assert precisely those behaviours plus the fail-closed / idempotency
invariants. No speculative scope — the warn-then-enforce ramp and a
`spec_impact`-gate extension were both consciously rejected in the iterate.

## Chesterton-Fence Check

`finalize_iterate.py` and `group_d.py` are large because each centralises one
cohesive responsibility with its "why" comments and (for the audit) many
independent drift classes; git history shows growth under that same structure
(ADR-090 granted `finalize_iterate`'s prior exception; ADR-095 the sibling
audit files). Extending the fence for a real correctness fix is consistent with
it, not a violation.

## Decision

Raise the four entries to their post-change measurements (`state: exception`,
`adr: ADR-096`):

| File | new current |
|---|---|
| `shared/scripts/tools/finalize_iterate.py` | 532 |
| `plugins/shipwright-compliance/scripts/audit/group_d.py` | 465 |
| `shared/tests/test_finalize_iterate.py` | 464 |
| `plugins/shipwright-compliance/tests/test_audit_groups_a_d.py` | 789 |

`finalize_iterate.py` was already exception under ADR-090; its `adr` is
re-pointed to ADR-096 (the controlling reason for the current measurement),
mirroring how ADR-095 re-pointed `audit_staleness`/`test_audit_snapshot`.
`group_d.py` and the two test files move `grandfathered` → `exception`.
`record_event.py` stays at 797 (the SSoT docstring fix was net-neutral) and is
untouched. Retire when `finalize_iterate` / the detective-audit groups + suites
are split (Re-Review-Date / the B/C bloat campaigns).

## Consequences

The four files now operate against the new limits; further additions must stay
within them or bump again with justification. The heaviest new logic (the gate
decision itself) reused `record_event`'s existing single-source-of-truth
function rather than adding a second copy, so no net algorithmic bloat was
introduced. C4 (webui repo: `g2_stoplist` + reopen-event FR reconcile) is out of
scope here.

## Rejected alternatives

- **Split `finalize_iterate` / `group_d` now** — disproportionate: pre-existing
  450–530 LOC deep modules; C3 adds small functional growth + required
  regression tests, not a structural problem. Splitting churns well-tested
  modules mid-fix and belongs to the dedicated bloat-cleanup campaigns.
- **Trim comments / extract `FinalizeGateError` to dodge the bump** — theatre
  (ADR-095's standing finding): shaving explanatory "why" off the write-path's
  fail-closed contract degrades clarity without addressing the legitimate
  growth. The conscious ADR + baseline update IS the check.
- **Skip the regression tests** — unacceptable: the empirical-completeness gate
  mandates them; without them a future change could silently reopen the bypass
  or re-break D3.

---

## External Sources Acknowledged

The YAGNI Check + Chesterton-Fence Check headings follow the bloat-exception
template, adapted from obra/superpowers `writing-plans` (MIT © Jesse Vincent)
and addyosmani/agent-skills `code-simplification` (MIT © Addy Osmani). The
Incident-Reference field follows the pattern of multica-ai/multica `CLAUDE.md`
(Apache-2.0 modified-with-hosting-restriction — pattern reused, text not).
