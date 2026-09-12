# Mini-Plan: t6 — AC-proving tests for FR-01.02 (/shipwright-project) + FR-01.16 (Guided requirement elicitation)

Campaign: `req3-05-test-backfill-mono`. Run-ID: `iterate-2026-09-12-t6-project-elicitation`.
Branch: `iterate/campaign-req3-05-test-backfill-mono-t6`.

## Problem statement

25 ACs (`FR-01.02` AC01–AC15, `FR-01.16` AC01–AC10) are listed `unbound` in
`shipwright_ac_coverage_baseline.json`: no `@pytest.mark.covers` test binds them.
Declared test roots — cited verbatim from the t0 seam survey's Master mapping
table (`.shipwright/planning/iterate/2026-09-11-req3-05-seam-survey.md`, the
`FR-01.02` and `FR-01.16` rows):

> `FR-01.02` | `/shipwright-project` | 15 / 15 | `plugins/shipwright-project/tests`
> | `test_integration.py` (drives `setup_session.py` end to end — the real
> skill entry point); `test_state.py`, `test_manifest.py`, `test_config.py`
> for individual ACs | none yet | t6
>
> `FR-01.16` | Guided requirement elicitation | 10 / 10 | `shared/tests`
> (single root — see harness column; code review confirmed AC09 is provable
> here alone, not a 3rd/4th root) | `shared/tests/test_requirement_elicitation_rigor.py`,
> `test_requirement_elicitation_discovery.py`, `test_requirement_elicitation_refs.py`;
> ... | none yet | t6

## Approach

1. Read the AC-evidence ledger
   (`.shipwright/planning/campaigns/2026-07-23-req3-ac-evidence-ledger-mono.md`)
   which already walked FR-01.02 (2026-07-24) and classified each of its ~15
   original criteria as `enforced, tested` / `prompt-only (judgement)` /
   `unimplemented`. Re-verify each classification is still current (the ledger
   predates the 2026-09-11 `e2-checks-project-elicitation` iterate that closed
   four of those rows) and map the ledger's `#N` numbering onto the current
   spec.md `AC01..AC15` numbering (the two orders correspond 1:1, verified
   bullet-by-bullet against `.shipwright/planning/01-adopted/spec.md`).
2. For every AC with genuine ENFORCED code (a `GateResult`-returning function
   wired into `run_project_checks`, or the P4.2 grill-trace gate), tag the
   existing pure-function-level test that already exercises that exact
   behaviour — never the wrapper-level integration test alone, and never a
   test that only proves the wrapper is *wired* without proving the
   underlying rule.
3. For every AC that is genuinely **prompt-only** per
   `requirement-elicitation.md` §6's own three-way verdict (enforced /
   prompt-only / contradicted — "prompt-only ... no behavioural test is
   possible. Only a drift test asserting the instruction is still present"),
   bind it to a drift test that pins the RULE SENTENCE in the doc that
   states it, not merely the section heading. Two such drift tests did not
   exist yet (FR-01.16 AC06's ADR-at-the-moment rule, AC08's
   confirm-before-writing rule) and one existing rulebook test scoped only
   to the `adopt` surface's doc, never the `project` surface's own copy
   (FR-01.02 AC09's plain-language rule) — new tests were written for these
   three; every other prompt-only AC already had a genuine drift test to tag.
4. For ACs where no instruction exists anywhere (FR-01.02 AC03, AC04 — no
   doc anywhere instructs a completeness cross-check or a scope-invention
   ban) or where the only real seam sits in a test root outside this unit's
   two declared roots (FR-01.02 AC01's `_validate_project` lives only in
   `plugins/shipwright-run/tests`; FR-01.02 AC15's "number stays permanently
   taken" clause is only checked in `plugins/shipwright-compliance/tests`
   / `shared/scripts/tests`), record the AC unbound with the concrete reason
   and flag the root question for the campaign owner — mirroring t5's
   Exception-3 precedent (flag, never self-authorize).
5. Regenerate `shipwright_ac_coverage_baseline.json` from a freshly
   regenerated (but NOT committed — the manifest is the compliance phase's
   own artifact, refreshed wholesale at t7) `.shipwright/compliance/test-traceability.json`,
   via `check_ac_coverage_ratchet.py --write`.

## Alternatives considered

- **Writing brand-new tests for every AC from scratch**, ignoring the
  AC-evidence ledger's own five-week-old classification work. Rejected:
  the ledger already did the enforced/prompt-only/unimplemented judgement
  call per AC with cited evidence; re-deriving it from zero risks a
  different, undocumented judgement call replacing a reviewed one, and
  wastes the campaign's own prior investment.
- **Binding every AC to *something*, including a weak proxy**, to reach
  "25 of 25 bound". Rejected outright by the binding constraint on this
  sub-iterate's own spec: "A test shaped around the implementation it was
  written against does not count and will be rejected in review." A
  forced binding on AC01/AC03/AC04/AC15 would misrepresent what is actually
  checked.
- **Self-authorizing the 3rd/4th test root** the AC01/AC15 seams need.
  Rejected: the sub-iterate spec explicitly forbids this and requires
  flagging instead, mirroring t5's own precedent for the identical
  situation on FR-01.09 AC12/AC13.

## Result

21 of 25 ACs bound; 4 recorded unbound with reasons (2 flagged for a root
decision, 2 genuinely un-instructed). See the iterate ADR / F5c test-results
ledger for the full per-AC disposition table.
