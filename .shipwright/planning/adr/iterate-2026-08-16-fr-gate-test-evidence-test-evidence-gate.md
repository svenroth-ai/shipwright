# Behaviour-affecting, FR-declaring events must carry test evidence or a stated reason

## Context

`shared/scripts/tools/record_event.py` builds a `work_completed` event's
`tests` block purely from CLI args (`--tests-passed`/`--tests-total`); a
caller that passes none gets no block and nothing objects. Measured
2026-08-16: 48 of 119 recorded events (40%) declare FR(s) with no
`tests.total` at all. Because `_reconciliation.compute_reconciliation` keys
reconciliation on "touched without a later tested reference", never on age,
an FR touched by one of those 48 events stays permanently marked as
needing re-verification — there is no test evidence anywhere in the log to
satisfy it. Control Grade's `change_reconciliation` dimension read 13/20
behaviour-touched FRs this way, most of why the monorepo graded B.

## Decision

Add a third FR-gate, `missing_test_evidence_error`
(`shared/scripts/lib/fr_test_evidence_gate.py`), mirroring the existing
`change_type`/`none_reason` no-FR discipline (ADR-059) exactly rather than
inventing a second vocabulary: a `work_completed` event that is
behaviour-affecting (`spec_impact` ∈ add/modify/remove) AND names FR(s)
must carry `tests.total > 0` OR a valid one-line `no_tests_reason`
(same validation as `none_reason`: non-empty, single line, ≤280 chars, no
control chars except tab). A docs-only / behaviour-preserving iterate
(`spec_impact: none`) is never gated — that stays a legitimate no-test
case, same as before.

`fr_gates.run_fr_gates(event, project_root, caller)` now runs all three
gates in one call — classification → FR-existence → test-evidence — wired
identically into both write paths (`record_event.py`'s CLI `main()` and
`finalize_iterate.py`'s F5b `_record_event`), closing the exact bypass
ADR-059's own external review flagged as future hardening (finding #2/#8).

This run's own `work_completed` event is the backlog-closing instrument
(no separate reconciliation tool): `spec_impact: none` +
non-empty `affected_frs` naming the 9 reconcilable FRs + a real
`tests.total` from this run's own full-suite F0 run. `spec_impact: none`
with FRs present *references* those FRs (re-verifying them) without
claiming this run touched their behaviour — the BP-2 "reference without
touch" shape.

## What changed

1. `shared/scripts/lib/fr_test_evidence_gate.py` (new) —
   `missing_test_evidence_error`, the third gate.
2. `shared/scripts/lib/fr_gates.py` — `run_fr_gates` composes all three
   gates in order: classification, then FR-existence, then test-evidence.
   Existence before evidence: there cannot be test evidence for an FR id
   that names nothing, so a typo'd id should surface "that id doesn't
   exist" before "prove you tested it".
3. `shared/scripts/tools/record_event.py` — `--no-tests-reason` CLI flag,
   validated and serialized like `--none-reason`; CLI `main()` now calls
   `run_fr_gates` once instead of two separate gate calls.
4. `shared/scripts/tools/finalize_iterate.py` — F5b write path calls the
   same `run_fr_gates` (ADR-059 parity, closing the documented bypass).
   `FinalizeGateError` now carries a `code` attribute mirroring the
   triggering gate's own `error` key (was hardcoded
   `fr_gate_unclassified` for every rejection). A malformed explicit
   `tests` block in `event_extras` now fails closed
   (`fr_gate_malformed_tests_block`) instead of being silently swallowed
   by a generic exception handler.
5. Docs: `references/F7.md` (CLI), `F5b.md` (finalize),
   `F-finalize-bundle.md` (payload schema), `docs/hooks-and-pipeline.md`.
6. This run's own `work_completed` event (F5b of THIS run) references
   FR-01.01/04/05/07/08/10/12/13/15 with `spec_impact: none` and this
   run's real, exhaustively-measured `tests.total`.

## Consequences

- Every FEATURE/CHANGE/BUG iterate from this PR onward that declares FRs
  and is behaviour-affecting must record real test evidence or say why it
  cannot — the silent 40% hole cannot recur.
- `compute_reconciliation` over the post-merge event log reports the 9
  FRs above reconciled; FR-01.16/18/19 correctly remain
  needing-re-verification (no tests exist for them to re-run — they close
  via a separate AC-test-backfill card, trg-c4f877ab / REQ3.05).
- The 48 historical events are not backfilled — the log is append-only —
  so the raw "FRs without tests" count does not drop to zero; only new
  writes are protected.

## Known Limitations (from internal plan review, triaged)

- The 48/119 figure counts every FR-declaring event with no
  `tests.total`, including `spec_impact: none` ones this gate never
  touches (by design, AC-3) — the gate closes the write-time hole for the
  behaviour-affecting slice, not the raw count.
- `fr_test_evidence_gate.py`'s predicate is deliberately not unified with
  `_traceability._iterate_needs_tests` — one is a write-time hard gate,
  the other a read-time RTM heuristic; coupling them risks either
  softening the gate or hardening the heuristic. Revisit only if the two
  are found drifting in practice.
- Pre-existing bypasses are unchanged: `event_amended --fields` can merge
  FR fields into an already-recorded event without re-running any gate,
  and `no_tests_reason`/`none_reason` are free-form operator text, not
  independently verified. Both predate this card.
- A `FinalizeGateError` from a `tests` block that folded to nothing (e.g.
  a stale/foreign-run ledger) reports the generic
  `fr_gate_missing_test_evidence` detail, not the specific cause —
  `iterate_tests_block.fold_into_event` does not currently carry a reason
  code to surface. Deferred, smaller follow-up.

## Doubt Review (triaged)

Fixed (real defects):

- **Mislabeled rejection code.** `finalize_iterate.py`'s CLI hardcoded
  `fr_gate_unclassified` for every `FinalizeGateError`. `FinalizeGateError`
  now carries `code` from the triggering gate.
- **Silent swallow of a malformed explicit `tests` block.** A hand-typed
  `tests` block failing shape validation raised inside a generic
  `except Exception`, printing to stderr and continuing to a
  successful-looking finalize — vanishing the whole event. Now wrapped in
  its own `try/except ValueError`, re-raised as `FinalizeGateError`.
- **Gate order.** Evidence ran before existence; reordered so an unknown
  FR id is reported before "prove you tested it".

Rebutted (documented, not fixed):

- The gate reads only event-level `spec_impact`, never the per-FR
  `fr_impact` map (which reconciliation treats as authoritative when
  present) — a constructed event could bypass it via `fr_impact`. Inherited
  from ADR-059's own `fr_or_change_type_gate_error`, which has the same
  blind spot; the card's mandate was to mirror that gate's exact scope, not
  extend it. Cross-validating `fr_impact` against `spec_impact` at both
  gates is a separate, correctly-scoped follow-up.
- `no_tests_reason` has no read-side consumer and, like `none_reason`, is
  unverified operator text — a dishonesty vector that predates this card
  and that this card makes more likely to be *reached* (not a new surface).
  Giving it a read-side consumer (a detective check counting hatch usage)
  is a real, additive follow-up, not part of closing this write-time hole.

## Review

Reviewed by the standard cascade for this iterate (spec-reviewer,
code-reviewer, doubt-reviewer). spec-reviewer found a missed third pytest
root silently relying on the hole. code-reviewer found coverage gaps,
naming/message inaccuracies and a fragile assertion. doubt-reviewer's two
fixed findings are recorded above. All fixed and re-verified before commit.

## External-Code-Review-Findings

OpenRouter cascade ran on the code diff (`openai` succeeded, `deepseek`
returned an empty reply — degraded, not a finding). 1 finding.

| # | Source | Severity | Finding | Disposition |
|---|--------|----------|---------|--------------|
| 1 | OpenAI | HIGH | AC-5 (this run's own `work_completed` event, closing the reconciliation backlog) is not visible in the reviewed diff — the reviewer could not confirm the real event was ever recorded. | accepted-and-already-satisfied — the reviewer was given only the code diff (`review-diff.txt`), which correctly excludes AC-5 (it is an event, not code, per the spec's own scope note). The real event (`evt-bf6245fb`, `spec_impact: none`, the 9 FRs, `tests.total: 16212/passed: 16160`) was already recorded via `finalize_bundle.py`'s F5b step before this review ran. A local `compute_reconciliation` re-check after that write confirmed the 9 FRs reconciled and only FR-01.16/18/19 still needing re-verification — the exact outcome the reviewer asked to see verified. |

## See also

- Iterate spec: `.shipwright/planning/iterate/iterate-2026-08-16-fr-gate-test-evidence.md`
- Mini-plan: `.shipwright/planning/iterate/iterate-2026-08-16-fr-gate-test-evidence-miniplan.md`
- Prior gate this mirrors: ADR-059 (`fr_or_change_type_gate_error`)
- Generators: `shared/scripts/lib/fr_test_evidence_gate.py`,
  `shared/scripts/lib/fr_gates.py`
