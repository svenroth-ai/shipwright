# Mini-Plan: e6-judgement-drift-tests

## Problem

`sub-iterates/e6-judgement-drift-tests.md`'s two acceptance criteria: "Each
of the 19 lines has a drift test on its instruction text" and "No judgement
line gained a pass/fail gate on content" — governed by campaign decision D7
(naive LLM-judge flag rate 98%, purpose-built precision 0.52-0.66, ignored
within weeks). The spec's own "19" is asserted, not authoritative, and the
spec explicitly instructs verifying it against the live ledger rather than
trusting it.

## Investigation (done before writing any test)

Ran `uv run shared/scripts/tools/measure_ac_evidence_ledger.py`: **31**
backtick occurrences of `prompt-only (judgement)` document-wide (not 19 —
the campaign card's count is from 2026-09-06, before `e1`-`e5` and two
external P4.2/P4.4 iterates each split several mechanisable rows into new
judgement halves per D7's own abort condition). Grepped every occurrence and
classified by hand:

- 6 are not criterion rows at all: the legend definition, two abort-condition
  mentions in prose, one historical 2026-07-26 End-check table cell, and one
  row's own pointer to its split-out `3b` sibling.
- **25** are genuine per-criterion table rows — the real unit of work.

For each of the 25, checked whether a real drift test already exists (file +
function actually present and actually passing, not merely claimed in the
ledger's own prose) before writing anything new:

- **10** already had a real, cited, verified test (`e1`/`e2`/`e3`, P4.4).
- **6** already had a real test, just never cited back onto their own ledger
  row (FR-01.02 #6, FR-01.11 #4, FR-01.13 #2, FR-01.16 #1/#5/#7) — found by
  cross-referencing `shipwright_ac_coverage_baseline.json`'s bound/unbound AC
  list and grepping existing suites for the criterion's exact source
  sentence, not by trusting the ledger's own "no evidence" cell.
- **1** (FR-01.02 #4b) turned out not to be a judgement line at all: its
  mechanism, `verify_grill_trace_completeness.check_blank_dimension`, already
  enforces it for every grilled requirement (confirmed via the AC-coverage
  baseline: `FR-01.02/AC07` is bound, not unbound) — the row's status tag was
  stale, not a live gap.
- **8** genuinely had no test anywhere: FR-01.02 #1/#2, FR-01.05 #2/#3,
  FR-01.08 #8's confirms-first half, FR-01.09 #1's request-opening half,
  FR-01.12 #2/#6's addressing half.

## Decision

1. Write exactly one new drift test per genuinely-untested row (8 total) —
   each asserts the governing instruction's exact sentence (or, where the
   text soft-wraps in the source markdown, its whitespace-normalized form)
   is still present in its source doc. No scoring, no LLM call, no
   heuristic — a literal substring assertion, per D7.
   - `shared/tests/test_requirement_elicitation_rigor.py` (+2): FR-01.02
     #1/#2 — both source in `shared/requirement-elicitation.md` §8/§8.1.
   - `plugins/shipwright-build/tests/test_build_judgement_drift.py` (new,
     +2): FR-01.05 #2/#3 — source in `agents/spec-reviewer.md`.
   - `plugins/shipwright-deploy/tests/test_deploy_judgement_drift.py` (new,
     +1): FR-01.08 #8 confirms-first — source in `skills/deploy/SKILL.md`'s
     Manual Rollback section.
   - `plugins/shipwright-preview/tests/test_preview_judgement_drift.py`
     (new, +2): FR-01.12 #2/#6 — source in `skills/preview/SKILL.md`.
   - `plugins/shipwright-changelog/tests/test_changelog_judgement_drift.py`
     (new, +1): FR-01.09 #1 request half — source in
     `skills/changelog/SKILL.md` Step 7.
2. Register the `covers` pytest marker in `shipwright-preview`'s
   `pyproject.toml` (it was the only touched plugin missing it) — test
   infrastructure hygiene, not a gate.
3. Correct the ledger: flip FR-01.02 #4b's status to `enforced, tested`
   with the mechanism citation (no new check built — a citation added to a
   pre-existing mechanism); add the missing test citations to the 6 rows
   found already covered; add a `Re-measured 2026-09-16` summary paragraph
   documenting the 19→25 discrepancy and the closure, matching the
   established `e0`-`e5` pattern.

## Explicitly not done (scope discipline per the spec's own warning)

No gate, scorer, or "semantic drift" helper of any kind. No production code
path changed. No ledger row's classification was loosened or upgraded to a
gate — the one status flip (#4b) moves a row to a classification an
existing, independently-built mechanism already earns; it does not build
anything to earn it.
