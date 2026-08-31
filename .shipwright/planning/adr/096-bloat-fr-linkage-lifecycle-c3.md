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

### Addendum 2026-08-04 (iterate-timing-attribution)

`finalize_iterate.py` 564 → 575 (+11): folds the new `iterate_timings` sidecar
into `work_completed` beside the existing `phase_timings` fold (one import +
two lines), and regenerates the derived iterate-throughput report at F5b (one
import + a `write_report_best_effort` call + the same `{written}/{skipped}`
result shape every other finalize step already uses). Both additions were
trimmed repeatedly before this addendum — the best-effort try/except was
pushed into `iterate_throughput_report.py` itself (a new, unconstrained file)
specifically to keep this hub file's growth to the minimum a caller genuinely
needs: one function call and one result-dict entry per new finalize step,
matching the shape `_update_compliance`/`_update_dashboard` already established.
No further reduction was available without breaking that established shape or
re-opening ADR-096's own Ousterhout argument (the gate belongs at the write
chokepoint, not scattered to dodge a line count). `564` (the ADR-096 → later
bump measurement already on file) is raised to `575`; `adr` stays `ADR-096` —
same controlling reason (this file legitimately absorbs new finalize-step
wiring), not a new exception class. Re-Review-Date unchanged.

### Addendum 2026-08-31 (compliance-error-surfacing)

`finalize_iterate.py` 575 → 587 (+12): `_update_compliance` used to log only
`result.stderr` on a non-zero `update_compliance.py` exit. On a
generator-error exit that script writes its diagnostic (`generator_errors`)
to STDOUT and leaves stderr EMPTY — the reverse of where the caller looked —
so the operator saw an empty `[finalize_iterate] compliance failed: ` line
with no clue what broke (surfaced during doubt-review of
iterate-2026-08-29-compliance-interpreter-fix; the same bug existed in the
two other callers, `finalize_security_compliance.py` and
`compliance_runner.py`, both far under their own bloat caps and fixed there
without needing an exception). The fix is one new private helper,
`_compliance_failure_detail` (10 lines: parse stdout JSON, extract
`generator_errors` if present, else fall back to the existing stderr slice),
called from the one `else` branch that used to read `result.stderr` directly;
+2 lines are the mandatory PEP8 blank-line separators around the new
function. Trimmed before this addendum: the helper's docstring was cut from
a 6-line explanation to one line (the "why" — stdout-not-stderr — is
preserved here instead, matching this file's own established pattern of
keeping rationale in the ADR rather than in-file when the in-file cost would
re-cross the ceiling); a standalone `shared/scripts/lib/` extraction was
tried first and rejected (see Rejected alternatives) because it added an
import line without recovering enough to matter. Same controlling reason as
the rest of this ADR — this file legitimately absorbs new finalize-step
wiring, and this is a correctness fix to an *existing* finalize step, not a
new one. `575` (the iterate-timing-attribution addendum's measurement) is
raised to `587`; `adr` stays `ADR-096`. Re-Review-Date unchanged.

**+1 further (587 → 588), same addendum:** the external code-review cascade
(openai via openrouter) found the helper assumed every truthy
`generator_errors` value was a list of dicts — a malformed-but-valid JSON
producer response (e.g. `{"generator_errors": "failure"}` or
`{"generator_errors": [null]}`) would raise `AttributeError` from `e.get(...)`
instead of falling back to stderr, silently losing the diagnostic the whole
fix exists to preserve. One added line (`valid = [e for e in errors if
isinstance(e, dict)] if isinstance(errors, list) else []`) filters to
well-shaped entries before formatting; falls back to the stderr slice when
nothing valid remains. Applied identically to the two sibling helpers
(neither needed an exception bump). `588` is the new `current`.

## Consequences

The four files now operate against the new limits; further additions must stay
within them or bump again with justification. The heaviest new logic (the gate
decision itself) reused `record_event`'s existing single-source-of-truth
function rather than adding a second copy, so no net algorithmic bloat was
introduced. C4 (webui repo: `g2_stoplist` + reopen-event FR reconcile) is out of
scope here.

### Amendment (2026-07-11, iterate-2026-07-11-iterate-phase-timing)

`finalize_iterate.py` had since shrunk and its baseline watermark ratcheted down
to 519. The Iterate-Rail per-phase-timing fold (M-Pre-1 iterate half, trg-8efeb3d7)
adds +5 lines (one import + a 3-line best-effort `_fold_phase_timings(event, …)`
call in `_record_event`), re-raising the watermark **519 → 524**. This stays
**within the 532 ceiling this ADR already granted** — no new crossing, just
reclaimed headroom — and the heavy logic lives in the new deep module
`shared/scripts/lib/iterate_phase_groups.py`, not here. The gate INSIDE
`_record_event` remains the right home for a per-event enrichment, same rationale
as the Ousterhout argument above.

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
- **(2026-08-31 addendum) Extract `_compliance_failure_detail` into a new
  `shared/scripts/lib/` module instead of bumping the ceiling** — tried first,
  rejected: the extraction still needs one `from lib.… import …` line in this
  file (this file already imports six sibling `lib.*` helpers the same way),
  so it only traded 10 in-file lines for 1 import line — not enough to clear
  575, and it would make the two OTHER fixed callers
  (`finalize_security_compliance.py`, `compliance_runner.py`, both far under
  their caps) inconsistent with this one for no benefit, since neither imports
  from `shared/scripts/lib` today and both keep their own local copy of the
  same helper.

---

## External Sources Acknowledged

The YAGNI Check + Chesterton-Fence Check headings follow the bloat-exception
template, adapted from obra/superpowers `writing-plans` (MIT © Jesse Vincent)
and addyosmani/agent-skills `code-simplification` (MIT © Addy Osmani). The
Incident-Reference field follows the pattern of multica-ai/multica `CLAUDE.md`
(Apache-2.0 modified-with-hosting-restriction — pattern reused, text not).
