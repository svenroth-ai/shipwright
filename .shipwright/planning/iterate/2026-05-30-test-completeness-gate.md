# Iterate Spec — Test Completeness Ledger + Gate

- **Run ID:** `iterate-2026-05-30-test-completeness-gate`
- **Type:** change (evolves the Confidence Calibration phase) + add (new verifier gate)
- **Complexity:** medium (classifier said `trivial`@0.6 — under-estimate; cross-cutting skill discipline + new enforced verifier + drift-test updates)
- **Status:** draft

## Goal

Make "have you empirically tested everything testable?" structurally
self-answering, so the operator never has to ask before a merge. Replace
the Confidence Calibration **escape hatch** ("Edge cases NOT probed + why
acceptable") with a **Test Completeness Ledger**: every testable behavior
the diff introduces/changes is either `TESTED` (with evidence) or
`UNTESTABLE` (with a falsifiable, closed-vocabulary structural reason).
"Testable-but-untested = 0" is enforced by a fail-closed verifier at F11.

## Acceptance Criteria

- [ ] (AC1) `check_test_completeness_ledger` FAILs (ERROR) when
  `iterate_latest.test_completeness.counts.untested_testable > 0`.
- [ ] (AC2) FAILs when an `untestable` row has a `reason_code` outside the
  closed vocabulary (`UNTESTABLE_REASON_CODES`).
- [ ] (AC3) FAILs when the block is missing for a small/medium/large
  feature/change/bug iterate.
- [ ] (AC4) SKIPs at trivial complexity (auto `n/a`; no hard gate).
- [ ] (AC5) PASSes when every behavior is `tested` or valid `untestable`
  and `untested_testable == 0`.
- [ ] (AC6) `run_all_checks` includes the new check (F11 enforces it; a
  non-zero `verify_iterate_finalization.py` STOPs the run).
- [ ] (AC7) `status == "n/a"` at small+ FAILs without a `justification`,
  PASSes with one.
- [ ] (AC8) Enumeration cross-check: when `enumeration_basis` reports
  uncovered ACs, the check FAILs (guards a vacuous pass via
  under-enumeration).
- [ ] (AC9) SKILL.md Step 7.5 + the Path A spec template carry the Test
  Completeness Ledger; the phase-matrix drift tests are updated and green.
- [ ] (AC10) `confidence-anti-patterns.md` documents the Coverage Stopping
  Rule + the closed `UNTESTABLE` vocabulary; a reverse-drift test asserts
  the doc lists exactly the code's vocabulary.

## Spec Impact

- **Classification:** none (framework/process change — no target-app FR;
  this repo's own `spec.md` files are unaffected)
- **NONE justification:** This iterate changes the iterate *skill's* testing
  discipline and a shared verifier. It introduces no user-visible
  application requirement; it is tooling/process. Recorded at F7 as
  `spec_impact=none` with this justification.

## Out of Scope

- No production-time orchestrator script for completeness (we follow the
  `check_spec_impact_recorded` single-verifier pattern, not the
  `surface_verification.py` dual-layer pattern). The F11 verifier is the
  fail-closed point.
- No change to F0.5 surface-verification logic or wording (its consistency
  test must stay green).
- No auto-generation of the ledger from the diff (the runner authors it;
  the enumeration cross-check guards under-filling). AST-derived
  enumeration is a future enhancement.
- Renaming the "Confidence Calibration" phase (kept, to bound churn).

## Affected Boundaries

| Producer (writes) | Consumer (reads) | Format |
|---|---|---|
| iterate F5 (agent) writes `iterate_latest.test_completeness` | `check_test_completeness_ledger` | JSON block in `shipwright_test_results.json` |
| `UNTESTABLE_REASON_CODES` (frozenset in `iterate_checks.py`) | `confidence-anti-patterns.md` prose + reverse-drift test | closed vocabulary of reason codes |
| iterate spec `## Confidence Calibration` ledger table (hand-edited) | human reviewer / F11 summary | Markdown table |

`shipwright_test_results.json` is a `*_config`-shaped JSON the agent edits
by hand → `touches_io_boundary`-adjacent. Round-trip of the block shape is
covered by the verifier tests (malformed / partial / missing block cases).

## Confidence Calibration

- **Boundaries touched:** the `test_completeness` JSON block (producer F5 →
  consumer verifier); the closed reason-code vocabulary (code → doc).
- **Empirical probes run:** populated at F5 from the Test Completeness
  Ledger below — each AC above maps to a verifier unit test executed
  against a fixture `shipwright_test_results.json`.
- **Test Completeness Ledger:** see the table below (the new third bullet —
  replaces "Edge cases NOT probed + why acceptable").
- **Confidence-pattern check:** asymptote (depth) + coverage (breadth) — not
  done until every AC row is `tested` AND one boundary probe of the JSON
  block shape returns no finding.

### Test Completeness Ledger (this iterate)

| # | Testable behavior | Disposition | Evidence / reason_code |
|---|---|---|---|
| 1 | untested_testable>0 → FAIL | tested | `test_completeness_*::test_untested_testable_fails` |
| 2 | bad reason_code → FAIL | tested | `..::test_bad_reason_code_fails` |
| 3 | missing block at small+ → FAIL | tested | `..::test_missing_block_small_plus_fails` |
| 4 | trivial → SKIP | tested | `..::test_trivial_skips` |
| 5 | all-covered → PASS | tested | `..::test_all_covered_passes` |
| 6 | n/a w/o justification → FAIL; w/ → PASS | tested | `..::test_na_requires_justification` |
| 7 | enumeration gap → FAIL | tested | `..::test_enumeration_gap_fails` |
| 8 | included in run_all_checks | tested | `..::test_in_run_all_checks` |
| 9 | doc lists exactly code vocab | tested | `test_untestable_vocab_doc_sync` |
| 10 | phase-matrix/template drift updated | tested | `test_skill_phase_matrix.py` (updated) |
| — | live operator UX of the F11 summary line | untestable | `requires-manual-visual-judgment` (prose surfaced in PR body; asserted only structurally) |

## Verification (medium+)

- **Surface:** cli — `uv run pytest shared/tests/test_verify_iterate_finalization.py
  plugins/shipwright-iterate/tests/` against fixtures.
- **Runner command:** the F0.5 cli runner over the verifier + drift tests.
- **Evidence path:** `.shipwright/runs/{run_id}/surface_verification.json`.
