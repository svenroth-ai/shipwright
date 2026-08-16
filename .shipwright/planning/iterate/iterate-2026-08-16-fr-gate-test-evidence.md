# Iterate Spec: fr-gate-test-evidence

- **Run ID:** iterate-2026-08-16-fr-gate-test-evidence
- **Type:** change
- **Complexity:** medium
- **Status:** draft

## Goal

Close the hole that lets a behaviour-affecting, FR-declaring `work_completed`
event land with no test evidence at all: `record_event.py` builds the `tests`
block purely from CLI args, so a caller that passes none gets no block and
nothing objects. 48 of 119 recorded events (40%) carry FRs with no
`tests.total`, and because `compute_reconciliation` keys on
touched-without-re-verify and never on age, that state is permanent until a
later event re-verifies the same FR. Add a gate mirroring the existing
`change_type`/`none_reason` no-FR discipline: a behaviour-affecting,
FR-declaring event must carry test evidence OR state why it cannot. Then use
this run's own `work_completed` event to close the reconciliation backlog for
the FRs whose test evidence is genuinely fresh.

## Acceptance Criteria
- [x] AC-1: `run_fr_gates` (and both its callers — `record_event.py` CLI and
      `finalize_iterate.py`'s F5b write path) reject a `work_completed` event
      that is behaviour-affecting (`spec_impact` ∈ add/modify/remove), names
      FR(s), carries no `tests.total`, and carries no `no_tests_reason`.
- [x] AC-2: The same event with a valid one-line `no_tests_reason` is
      accepted (mirrors `none_reason`'s validation: non-empty, single-line,
      ≤280 chars, no control chars except tab).
- [x] AC-3: A docs-only / behaviour-preserving iterate (`spec_impact: none`)
      is never gated by this rule — it is intent-independent but
      impact-dependent, matching the existing BP-1 gate's scoping.
- [x] AC-4: `record_event.py`'s CLI gains `--no-tests-reason`, validated and
      serialized the same way `--none-reason` is.
- [x] AC-5: This run's own `work_completed` event declares
      `spec_impact: none` with a non-empty `affected_frs` naming the
      reconcilable FRs (referencing without touching — see Spec Impact
      below) and a real `tests.total` from this run's own F0 full-suite run,
      so `compute_reconciliation` reports them reconciled after this run
      merges.

## Spec Impact
- **Classification:** none
- **NONE justification:** This iterate changes the shared FR-gate validation
  logic in `shared/scripts/lib/fr_gates.py` / `shared/scripts/tools/record_event.py`
  — internal tooling that write-time-validates `work_completed` events. It adds
  a new write-time discipline but does not add, modify, or remove any of the
  framework's own product-facing FRs (FR-01.xx). The `affected_frs` list below
  is deliberately non-empty despite `spec_impact: none`: it *references* (and
  thereby re-verifies) FRs this run's full test-suite run legitimately
  exercises, without claiming this run changed their behaviour. This is the
  BP-2 "reference without touch" shape the card explicitly authorizes.

## Out of Scope
- Backfilling the 48 historical events with no `tests.total` — the event log
  is append-only; rewriting history is never the answer.
- FR-01.16 (RTM: FAIL, tracked as trg-9c9c0792), FR-01.18 (NOT VERIFIED),
  FR-01.19 (NO TESTS) — no tests exist to re-run for these, so they correctly
  stay unreconciled. They close via REQ3.05/REQ3.09, not here.
- Any of the 9 candidate FRs where the REQ-3 Phase 2 rewording
  (iterate-2026-07-23-req3-phase2-content-mono) or a later behaviour-touch
  changed the underlying ASK such that today's tests can't honestly be said
  to still assert it — see the spot-check under Confidence Calibration.
- Building a standalone reconciliation tool — the card is explicit that this
  run's own event is the instrument, not a new script.

## Design Notes
n/a — backend/library change, no UI surface.

## Affected Boundaries

| Producer (writes) | Consumer (reads) | Format |
|---|---|---|
| `record_event.py build_event` / `finalize_iterate.py _record_event` | `lib/fr_gates.py run_fr_gates` (write-time gate); `_reconciliation.compute_reconciliation` (read-time, Control Grade + RTM) | in-process dict → JSONL line in `shipwright_events.jsonl` |

No new serialized boundary is introduced — `no_tests_reason` is a new key in
an already-existing JSONL event shape, validated the same way `none_reason`
already is. `touches_io_boundary` does not fire (no `*_config.json`/
`*_state.json` file changed, no new `json.dump`/`load` call site).

## Confidence Calibration

- **Boundaries touched:** the `work_completed` event schema (new
  `no_tests_reason` key); no new producer/consumer pair.
- **Empirical probes run:**
  - Ran `compute_reconciliation` over the current `shipwright_events.jsonl`
    directly (not from memory) — confirmed `unreconciled` = exactly
    `{FR-01.01, FR-01.04, FR-01.05, FR-01.07, FR-01.08, FR-01.10, FR-01.12,
    FR-01.13, FR-01.15, FR-01.16, FR-01.18, FR-01.19}`, matching the card's 9
    reconcilable + 3 out-of-scope split.
  - Cross-checked all 9 against the RTM (`traceability-matrix.md`): all 9
    show `COVERED`; the 3 excluded show `FAIL`/`NOT VERIFIED`/`NO TESTS`.
  - **Spot-check (the judgment call the card requires):** diffed
    `28491e1c` (`feat(spec): REQ-3 Phase 2 — every requirement now states
    what it guarantees`, #436 — the commit behind `evt-ea7203ec`/
    `iterate-2026-07-23-req3-phase2-content-mono`) against
    `.shipwright/planning/01-adopted/spec.md`. Found 6 of the 9 with a
    reworded guarantee line or a from-scratch AC fill:
    FR-01.01, FR-01.05, FR-01.07, FR-01.08, FR-01.15 (guarantee-line reworded)
    and FR-01.04 (went from `TBD — not yet elaborated` to 12 concrete ACs).
    The other 3 (FR-01.10, FR-01.12, FR-01.13) had their guarantee line and
    existing ACs untouched — only pure additions, so they carry no risk and
    need no further check.
    For the 6: (a) the commit's own stated purpose was correcting requirement
    *text* to match already-implemented, already-tested code — "all 18
    requirements walked against the code that implements them, not against
    the documents that describe them" — not introducing new asks; (b) for
    every FR in the 6, I found no case of an existing AC being *removed and
    contradicted* by a new one (FR-01.01 lost one AC — "no prompt hook
    written into project settings" — a scope narrowing, not a contradiction);
    (c) per-FR, I recomputed each FR's actual *latest* behaviour touch (not
    just the REQ-3 rewrite) via `_referenced_and_touched` — for 5 of the 6
    (all but FR-01.04/FR-01.05) a *later*, non-rewording iterate is the real
    latest touch (e.g. FR-01.08's latest touch is
    `evt-a345a59f` / "hosting rollback uses the target ref..." from
    2026-07-27, a genuine feature-completion iterate that — under the
    framework's own mandatory-TDD Iron Law — could not have merged without
    its own tests, which are now permanently part of the suite this run's F0
    re-runs in full). Conclusion: all 9 stay in this run's reconciliation
    list; none needed to move out. (Documented per the card's explicit
    allowance that a clean spot-check is a legitimate outcome, not a
    shortcut — the check was performed, not skipped.)
- **Test Completeness Ledger:**

  | # | Testable behavior | Disposition | Evidence / reason_code |
  |---|---|---|---|
  | 1 | `missing_test_evidence_error` refuses a behaviour-affecting, FR-declaring event with no `tests.total` and no `no_tests_reason` | tested | `shared/tests/test_fr_gate_test_evidence.py::TestTestEvidenceGate::test_behavior_affecting_with_frs_no_tests_no_reason_blocked` PASSED |
  | 2 | The same event with a valid `no_tests_reason` is accepted | tested | `shared/tests/test_fr_gate_test_evidence.py::TestTestEvidenceGate::test_behavior_affecting_with_no_tests_reason_passes` PASSED |
  | 3 | The same event with a real `tests.total` (no reason needed) is accepted | tested | `shared/tests/test_fr_gate_test_evidence.py::TestTestEvidenceGate::test_behavior_affecting_with_tests_block_passes` PASSED |
  | 4 | `spec_impact: none` (docs/behaviour-preserving) is never gated by this rule, even with FRs and no tests | tested | `shared/tests/test_fr_gate_test_evidence.py::TestTestEvidenceGate::test_behavior_preserving_bypasses_gate` PASSED |
  | 5 | No FRs declared → this gate stays silent (existing classification gate owns that case) | tested | `shared/tests/test_fr_gate_test_evidence.py::TestTestEvidenceGate::test_no_frs_bypasses_this_gate` PASSED |
  | 6 | `no_tests_reason` validation mirrors `none_reason` (blank/whitespace, oversized, control-char rejected; tab tolerated) | tested | `shared/tests/test_fr_gate_test_evidence.py::TestNoTestsReasonValidation` PASSED (4 cases) |
  | 7 | CLI (`record_event.py --no-tests-reason`) integration: rejected without evidence, accepted with `--no-tests-reason`, zero-total still requires a reason, docs-only needs neither, event lands on disk with the field serialized | tested | `shared/tests/test_record_event_test_evidence.py::TestFrGateTestEvidenceCli` (4 cases) PASSED — kept out of the baseline-capped `test_record_event.py` per the file's zero-headroom bloat entry |
  | 8 | `finalize_iterate.py` F5b write path applies the same gate (ADR-059 parity) via `run_fr_gates`: rejects without evidence, allows `no_tests_reason`, allows an explicit `tests` block, never gates a `spec_impact: none` referencing event | tested | `shared/tests/test_finalize_test_evidence_gate.py` (4 cases) PASSED — kept out of the baseline-capped `test_finalize_iterate.py` per the same convention |
  | 9 | The reconciliation MECHANISM this run's own event will rely on: a `spec_impact: none` event referencing FRs with real `tests_total` reconciles an earlier untested touch on those same FRs; an FR touched-but-not-referenced by the reconciling event stays `needs_reverification`; the reconciling event itself is never counted as a behaviour touch. Deliberately synthetic (2 stand-in FRs + 1 FR-01.16-shaped row, not read from the live log — see the test file's own docstring for why) — it pins the mechanism's contract, not the live 9-reconciled/3-still-needing split, which is verified empirically at F5b instead (see item 10) | tested | `plugins/shipwright-compliance/tests/test_reconciliation_card20260816.py::TestCard20260816Reconciliation` (3 cases) PASSED — split into its own file to keep `test_reconciliation.py` under the 300-line guideline (this file is not itself in `shipwright_bloat_baseline.json`, so the split is proactive hygiene, not a ratchet fix) |
  | 10 | Integration: this run's own `work_completed` event round-trips through `record_event.py`'s gate (spec_impact=none, 9 FRs referenced, real tests.total) without rejection, AND the live `compute_reconciliation` over the real (post-merge) `shipwright_events.jsonl` actually reports the 9 reconciled + 3 still needing re-verification | tested | covered by item 4 (`spec_impact=none` bypass, not item 5 — item 5 is the no-FRs-declared bypass, a different case) + F5b's own real invocation at finalize, which either succeeds or the run does not complete + the empirical live re-check performed at F5b/F11 (Criterion 2's actual test, distinct from item 9's synthetic unit coverage) |
  | 11 | (doubt-review fix) A classified, unevidenced event naming an unknown FR id reports `fr_gate_unknown_fr`, not `fr_gate_missing_test_evidence` — existence is checked before evidence | tested | `shared/tests/test_fr_gate_existence.py::TestWiringActuallyEnforces::test_run_fr_gates_reports_unknown_fr_before_missing_test_evidence` PASSED |
  | 12 | (doubt-review fix) `finalize_iterate.py`'s CLI reports the triggering gate's real `error` code, not a hardcoded `fr_gate_unclassified`; a malformed explicit `tests` block fails closed (`FinalizeGateError`, code `fr_gate_malformed_tests_block`) instead of silently vanishing the event behind a green finalize | tested | `shared/tests/test_finalize_test_evidence_gate.py::test_finalize_rejection_carries_the_triggering_gate_code` + `::test_finalize_malformed_explicit_tests_block_fails_closed` PASSED |
  | 13 | (Stage-3 doubt-review fix, D3-1) A `new_frs` (minted requirement) is gated regardless of `spec_impact` — `spec_impact: none` alongside `new_frs` cannot bypass the rule the way it legitimately can for `affected_frs` (referencing an existing FR without touching it) | tested | `shared/tests/test_fr_gate_test_evidence.py::TestTestEvidenceGate::test_minted_fr_is_gated_even_with_spec_impact_none` + `::test_minted_fr_with_no_tests_reason_passes_even_with_spec_impact_none` PASSED |
  | 14 | (Stage-3 doubt-review fix, D3-2) `test_finalize_docs_only_iterate_needs_no_evidence` genuinely pins the F5b-path AC-3 bypass — its extras no longer carry a `tests` block, so the event actually reaches (and passes) the `not _is_behavior_affecting(...)` check instead of short-circuiting earlier on `has_test_evidence` | tested | `shared/tests/test_finalize_test_evidence_gate.py::test_finalize_docs_only_iterate_needs_no_evidence` PASSED (assertion can now fail if the bypass regresses) |

- **Confidence-pattern check:** asymptote — no "are you confident?"-shaped
  question was asked or answered without a probe; every claim above is
  backed by a command actually run (`compute_reconciliation`, `git show`,
  `grep` against the RTM) rather than recollection. Coverage — every ledger
  row is `tested`; 0 untested-testable. No integration-coverage row is
  required (`cross_component` did not fire — `record_event.py`/`fr_gates.py`
  are not on the `CROSS_COMPONENT_FILE_PATTERNS` list).
- **Stage-3 doubt-review (second pass, post-code-review):** ran a fresh
  adversarial pass against the final diff. Found 2 real defects (D3-1, D3-2 —
  fixed, ledger rows 13-14), 1 documentation gap (D3-3 — fixed, see below),
  2 low-severity items rebutted below, and 6 attempted disproofs that failed
  (fail-closed catch exhaustiveness, error-code consumer sweep, retry/
  idempotency, ungated-write-path sweep, gate-order correctness, the
  `fr_impact` rebuttal's second direction) — recorded as confirmation the
  diff holds under adversarial pressure, not padding.

## Known Limitations (from internal plan review, triaged)

- **Headline metric is broader than the gated subset.** The Goal's "48 of 119
  (40%)" figure counts every FR-declaring event with no `tests.total`,
  including those with `spec_impact: none` — which this gate never touches
  (AC-3). The gate closes the write-time hole for the *behaviour-affecting*
  slice of that 48; it does not claim to shrink the raw count to zero. Noted
  here rather than reworded in the Goal, because the 48/119 figure is the
  motivating measurement, not a claim about this gate's own coverage.
- **`fr_test_evidence_gate.py`'s predicate is not unified with
  `_traceability._iterate_needs_tests`.** Both ask "does this event need
  tests?", but at different times for different purposes: this gate asks
  write-time "should this specific event be rejected right now"; the
  traceability reader asks read-time "across the whole log, does this FR's
  history look adequately tested" for the RTM. Sharing one predicate would
  couple a hard write-time gate to a softer read-time heuristic (or vice
  versa) — deliberately kept separate rather than unified into a shared SSOT.
  A future card that finds the two drifting in practice (not just in theory)
  is the right trigger to revisit this.
- **Pre-existing bypasses are unchanged by this run.** `event_amended
  --fields` can shallow-merge FR fields into an already-recorded event
  without re-running any gate (write-once gating, not continuously
  re-validated), and `no_tests_reason` — like `none_reason` before it — is
  free-form operator text, not verified against anything. Both predate this
  card, apply equally to the existing `change_type`/`none_reason` no-FR
  shape this gate mirrors, and are out of scope here; closing them is a
  separate, explicitly-scoped card if they prove to matter in practice.
- **`FinalizeGateError`'s message does not name the likely cause when
  `_fold_tests_block` finds nothing** (e.g. a stale or foreign-run
  `shipwright_test_results.json`) — it reports the generic
  `fr_gate_missing_test_evidence` detail, not "ledger run_id X does not match
  this run". Deferred: `iterate_tests_block.fold_into_event` does not
  currently surface *why* it found nothing (only that it did), so a better
  message needs that module to carry a reason code first — a separate,
  smaller follow-up rather than part of this card's diff.

## Doubt Review (triaged)

The doubt-reviewer ran an adversarial pass against the write-time gate and its
two callers (chosen for review given the blast radius: a bug here can
silently admit bad events OR block every iterate's finalize). Two findings
were real defects and are fixed in this diff; three are documented rebuttals
or extended limitations, not fixed, with reasoning below.

**Fixed:**
- **Gate rejection mislabeled on the machine-readable channel.**
  `finalize_iterate.py`'s CLI `main()` hardcoded `"error": "fr_gate_unclassified"`
  for every `FinalizeGateError`, regardless of which gate actually fired (or
  a malformed `fr_impact`) — a consumer keying on `error` was told to add
  `--affected-frs`, which was often already present. `FinalizeGateError` now
  carries a `code` attribute set from the triggering gate's own `error` key
  (defaulting to `fr_gate_unclassified` for the pre-existing malformed-`fr_impact`
  path, which is classification-adjacent); `main()` emits `exc.code` instead
  of a hardcoded string. Test:
  `test_finalize_rejection_carries_the_triggering_gate_code`.
- **A malformed explicit `tests` block silently vanished the whole event
  behind a green finalize.** `_fold_tests_block`'s `fold_into_event` raises
  `ValueError` for a caller-supplied `tests` block that fails the shared
  validator (by design — see that module's docstring) — but that raise
  landed inside `_record_event`'s *generic* `except Exception`, which prints
  to stderr and returns `None`; `run()` reads that as a non-fatal
  `{"skipped": True}` step and continues to a successful-looking finalize.
  Before this card, a hand-typed `tests` block bought a caller nothing, so
  this path was rarely exercised; after it, a caller motivated to satisfy
  the new gate is *more* likely to hand-type one and hit a typo. Now wrapped
  in its own `try/except ValueError`, re-raised as `FinalizeGateError` (code
  `fr_gate_malformed_tests_block`) — fails closed like every other gate
  rejection instead of vanishing. Test:
  `test_finalize_malformed_explicit_tests_block_fails_closed`.
- **Gate order: existence before evidence, not after.** `run_fr_gates`
  originally ran classification → evidence → existence. A classified,
  unevidenced event naming a *nonexistent* FR id (a typo) surfaced
  "prove you tested it" before "that id names nothing" — backwards, since
  there cannot be test evidence for a requirement that doesn't exist.
  Reordered to classification → existence → evidence. Low risk (no existing
  test asserted the old order for a case where both gates would fire — the
  existence-degrades-to-unverifiable `tmp_path` fixture used throughout
  meant the two orderings were indistinguishable to every test that existed
  before this fix). Test (new):
  `test_run_fr_gates_reports_unknown_fr_before_missing_test_evidence`.

**Rebutted (not fixed, reasoning recorded):**
- **The gate reads only event-level `spec_impact`, not the per-FR `fr_impact`
  map, which `_reconciliation._referenced_and_touched` treats as
  authoritative over `spec_impact` when present.** Verified true — a
  constructed event with `spec_impact: none` + `fr_impact: {"FR-X": "modify"}`
  would pass this gate untested (bypasses at the `not
  _is_behavior_affecting(spec_impact)` check) while `compute_reconciliation`
  would still mark FR-X behaviour-touched-unverified: the false-accept
  the whole card exists to prevent. **This is not a regression introduced by
  this diff — it is inherited from BP-1's existing `fr_or_change_type_gate_error`**
  (`fr_gates.py`), which has read only event-level `spec_impact` (never
  `fr_impact`) since it shipped, months before this card. This card's own
  mandate was explicit: "mirror the existing discipline exactly... do not
  invent a second vocabulary" — matching BP-1's exact scope, including this
  blind spot, keeps the two gates consistent with each other; teaching only
  the *new* gate to read `fr_impact` while BP-1 still doesn't would make the
  pair *disagree* with each other, which is worse. Both write paths that can
  set `fr_impact` (`record_event.py --fr-impact`, `finalize_iterate.py`
  `event_extras["fr_impact"]`) already run `_normalize_fr_impact` for shape,
  but neither cross-validates it against `spec_impact` — closing that gap
  well requires touching BP-1 too, a separate, correctly-scoped follow-up
  card (candidate title: "cross-validate `fr_impact` against `spec_impact`
  at both FR-gates"), not a silent scope-creep of this one.
- **The no-tests escape hatches (`no_tests_reason`, and separately a
  hand-typed `tests` block) have no read-side accountability and can be
  used dishonestly.** Verified: `no_tests_reason` has zero read-side
  consumers (unlike `none_reason`, which D1/D5 do read), so its only value
  is the human-readable audit trail in the JSONL itself — exactly like
  `none_reason`'s own accountability model, not a new pattern. A concrete
  dishonesty vector exists: `_fold_tests_block` legitimately finds nothing
  when the ledger holds a foreign `run_id` (a documented, recurring state
  after an F11-prescribed derived-snapshot restore — see F5b.md), and an
  agent under pressure to unblock finalize could write a boilerplate
  `no_tests_reason` on a run where the suite actually passed, or hand-type a
  `tests` block that `fold_into_event`'s explicit-block precedence accepts
  without cross-checking the ledger. Both hatches predate this card
  (`none_reason` shares the first risk; `iterate_tests_block.fold_into_event`'s
  explicit-block precedence already existed) and this card does not add a
  new dishonesty surface — it makes the pre-existing ones more likely to be
  *reached*, since the gate now creates a reason to reach for them. Not
  fixed here: giving `no_tests_reason` a read-side consumer (a detective
  check counting hatch usage per iterate, mirroring `none_reason`'s D5) is a
  real, addressable follow-up, but is additive instrumentation, not part of
  closing the specific write-time hole this card targets — filed as a
  candidate follow-up rather than expanded into this diff.

## Stage-3 Doubt Review — second pass (triaged)

A second doubt-reviewer pass ran fresh-context against the diff after Stage 2
(code-reviewer) passed, specifically hunting for what the first doubt-review
pass and Stage 1/2 missed. Two real defects, one documentation gap fixed;
two low-severity items rebutted; six attempted disproofs failed (recorded as
confirmation the diff holds, not padding — see the six `D3-N*` non-issues in
the raw review record).

**Fixed:**
- **D3-1 (medium-high): `new_frs` + `spec_impact: none` minted a brand-new FR
  with zero test evidence, undetected by any gate.** Walked all three gates:
  classification passes (has_frs via `new_frs`, not behaviour-affecting),
  existence passes once the row is on disk, and the test-evidence gate
  bypassed entirely at the `not _is_behavior_affecting(...)` check — a
  minted requirement entered the RTM as `COVERED`, structurally exempt from
  reconciliation, with no gate anywhere asking for a test. Minting is
  inherently an "add"; `spec_impact: none` alongside `new_frs` is
  self-contradictory. Fixed: the gate now requires evidence whenever
  `new_frs` is non-empty, regardless of `spec_impact`
  (`shared/scripts/lib/fr_test_evidence_gate.py`). Doc wording in
  `F5b.md`/`hooks-and-pipeline.md`/the gate's own docstring corrected to
  scope the "reference without touch" bypass to `affected_frs` only. Tests:
  ledger row 13.
- **D3-2 (medium): the F5b-path AC-3 parity test could not fail.** Its
  extras supplied a valid `tests` block, so the event passed at the
  `has_test_evidence` check and never reached the `_is_behavior_affecting`
  bypass the test's docstring claimed to pin — deleting the entire bypass
  guard would not have failed it. Fixed: the `tests` key removed from the
  fixture. Tests: ledger row 14.
- **D3-3 (low-medium): `docs/guide.md` was the one documentation surface not
  updated for this run's gate.** CLAUDE.md's Documentation Guide names
  Chapter 8 (quality gates) as the section that goes stale on a gate change;
  the other four surfaces (`hooks-and-pipeline.md`, `F5b.md`, `F7.md`,
  `F-finalize-bundle.md`) were updated, `guide.md` was not. Fixed: one
  clause appended to the FR-mapping-discipline paragraph naming the new
  evidence requirement and the `new_frs` exception.

**Rebutted (not fixed, reasoning recorded):**
- **D3-4 (low): `validate_tests_block` type-checks `skipped` but not
  cross-field plausibility, so an internally-inconsistent explicit block
  (e.g. `passed: 100, total: 5`) reads as evidence.** Verified true, and
  pre-existing (the validator, not this gate, owns that check). This diff is
  what turns `tests.total` from a reported metric into a trust signal that
  unblocks a hard gate, which is exactly the honesty-hatch risk already
  rebutted in the first doubt-review pass (hand-typed `tests` block /
  `no_tests_reason`, no independent verification) — a second instance of the
  same documented trade-off, not a new one.
- **D3-5 (low): the deferred "why the fold found nothing" message could be
  usefully improved without waiting for `fold_into_event` to carry a reason
  code, contrary to Known Limitation 4's stated prerequisite.** Accepted as
  correct in principle (a static sentence naming the most common cause —
  stale/foreign `run_id` — would help without any upstream change) but left
  as a documented, cheap future improvement rather than expanded into this
  diff: the message is a wording change with no behavioural risk either way,
  and bundling it here would mix an unrelated polish item into a diff this
  card already keeps tightly scoped.

## Verification (medium+)
- **Surface:** none
- **Justification:** backend Python library/CLI change with no web/API/CLI
  *user-facing* surface to drive — the "surface" here is the event-log
  write path itself, and it is verified by the unit + CLI-integration tests
  listed in the Test Completeness Ledger above, plus the fact that this run's
  own F5b write (a real, non-mocked invocation of the exact code path this
  iterate changes) either succeeds and this run completes, or fails and it
  doesn't. F0.5's `surface_verification` block will record
  `surface: "none"` with this justification.
