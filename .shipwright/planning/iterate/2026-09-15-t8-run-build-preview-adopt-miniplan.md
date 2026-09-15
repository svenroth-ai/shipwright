# Mini-Plan: t8 — AC-proving tests for FR-01.01 (/shipwright-run) + FR-01.05 (/shipwright-build) + FR-01.12 (/shipwright-preview) + FR-01.13 (/shipwright-adopt)

Campaign: `req3-05-test-backfill-mono`. Run-ID: `iterate-2026-09-15-t8-run-build-preview-adopt`.
Branch: `iterate/campaign-req3-05-test-backfill-mono-t8`.

## Problem statement

30 ACs (`FR-01.01` AC01-AC07, `FR-01.05` AC01-AC08, `FR-01.12` AC01-AC09,
`FR-01.13` AC01-AC04/AC06/AC07) are listed `unbound` in
`shipwright_ac_coverage_baseline.json` at the start of this run. Declared
roots (t0 seam survey, `.shipwright/planning/iterate/2026-09-11-req3-05-seam-survey.md`,
five roots, owner-accepted 2026-09-12 as the largest fan-out in the campaign):
`plugins/shipwright-run/tests`, `plugins/shipwright-build/tests`,
`plugins/shipwright-adopt/tests`, `shared/tests`, `shared/scripts/tests`.

## Approach

1. Re-derive the exact unbound AC ids from `shipwright_ac_coverage_baseline.json`
   (30, matching the spec's stated count) rather than trusting the spec text.
2. **FR-01.01** — read `orchestrator_pkg/*` for the real enforcing module per
   AC (constants.py's `PIPELINE_STEPS`/`_LEGACY_PIPELINE_ENTRIES` for AC06,
   `validation_record.py`/`update_step` for AC02/AC03, `single_session_loop.py`
   for AC01/AC05, `single_session_recovery.py`/`orchestrator_context.py` for
   AC04, `config_io.mode_rejection` for AC07). All 7 ACs found a real,
   already-passing test to tag; AC04 needed one new test
   (`test_reload_context_states_which_phase_was_interrupted`) because the
   existing suite proved "finished" and "failed" phase states but never the
   "in_progress" (interrupted) one AC04's second clause names.
3. **FR-01.05** — `/shipwright-build` has no `scripts/` implementation of the
   build behavior itself (only section-state tracking); the described
   behavior (write working code, read the mockup, stop on contradiction,
   stay in scope, deliver as one unit) is entirely `SKILL.md`/agent-executed
   prose, the same class Exception 1 already established for
   `/shipwright-preview`. One new negative-case test added
   (`test_complete_without_test_counts_is_rejected`) — the existing
   `TestInvalidPayloads` class had no test proving a `complete` payload
   omitting proof-of-tests entirely is rejected. This proves the schema
   REQUIRES `tests_passed`/`tests_total`, which is NOT the same as proving
   tests actually ran and passed — a required field is self-reported, not
   verified (external plan review, openai, HIGH) — so the test is kept,
   unmarked, as a regression guard only. All 8 ACs (AC01-AC08) recorded
   unbound with reason (seam survey Exception 9, written this run).
4. **FR-01.12** — t0's own Exception 1 already pre-assigned the AC-by-AC
   split; this unit executes it rather than re-deciding it. `shared/tests/`
   had **zero existing tests for `dev_server`** despite the module living in
   `shared/scripts/dev_server/`
   (`shared/tests/test_dev_server_multiservice.py` and siblings ARE the
   existing, dense, already-passing suite the survey's harness column names —
   they were simply untagged). AC04, AC05, AC06, AC08 tagged onto existing
   tests. AC01 (spawn half real, precondition half no-seam), AC02, AC03,
   AC07, AC09 stay unbound per Exception 1's own split table: "record BOTH
   halves" for AC01 means recording the unprovable precondition half
   alongside the provable spawn half, not tagging the AC as bound on the
   spawn half alone (external code review, openai HIGH + glm low, corrected
   after an earlier draft of this plan tagged AC01).
5. **FR-01.13** — dense, mature plugin with real seams for every AC but one.
   AC01 (a 4-clause conjunction: guidance + catalogue + audit evidence +
   starting tests) needed THREE existing tests, not one, to cover every
   clause (`test_full_pipeline_e2e_via_subprocess` for guidance+catalogue,
   `test_step_h_stamps_before_committing_and_verifies_after` for audit
   evidence, `test_write_to_filesystem`/`test_render_produces_valid_ts` for
   the starting E2E test scaffold) — no single existing test proved all four.
   AC02 (disjunctive: derived+unconfirmed marking, AND the count reported at
   handover) tagged across two existing tests, one per clause. AC03 (a
   tracked human follow-up) had a real, wired, but completely UNTESTED
   function, `catalogue_followup.confirmation_triage` — one new test file
   written (`test_catalogue_followup.py`, 3 tests) rather than binding to a
   wrapper. AC04 (disjunctive: failing tests OR untested capabilities, both
   "recorded as inherited") tagged across two existing tests, one per
   branch. AC07 (gateway routing + no-silent-fallback) tagged across the
   adopt-side reachability test and the shared `llm_review` routing test
   that already proves the fail-closed half. AC06 ("plain business language")
   has no deterministic seam anywhere in `feature_inferrer.py`/`spec_document.py`
   — label/description text is agent-authored, unmeasured; recorded unbound.
6. Regenerate `.shipwright/compliance/test-traceability.json` via the
   `test_links` collector (stale before this run — dev_server/adopt files
   were untagged) before regenerating `shipwright_ac_coverage_baseline.json`
   via `check_ac_coverage_ratchet.py --write`; leave the manifest
   uncommitted-but-present per t3-t7's established convention (CI's own
   fresh-regen step rebuilds it from real JUnit output).

## Alternatives considered

- **Writing brand-new tests for every AC from scratch.** Rejected for
  FR-01.01/FR-01.12/FR-01.13: each already had dense, real, passing coverage
  of the exact production code paths — the gap was tagging (or, for
  `dev_server`, tagging a suite that had simply never been AC-tagged at
  all), not testing. Three new test functions were written for genuine gaps
  (`test_reload_context_states_which_phase_was_interrupted`,
  `test_complete_without_test_counts_is_rejected`, and the 3-test
  `test_catalogue_followup.py` file) rather than as a first resort.
- **Binding FR-01.05's AC01-AC06/AC08 to a proxy** (e.g. the section-state
  recording mechanism, which accepts any string as a "commit" with no
  verification) to raise the bound count. Rejected outright by the binding
  constraint on this sub-iterate's own spec — a test shaped around what the
  implementation happens to accept, not around what the AC actually
  requires, is exactly what "no new harness where an existing one fits"
  and "must PROVE the AC" forbid. Recorded as Exception 9 in the seam
  survey instead, mirroring Exception 1's precedent for `/shipwright-preview`.
- **Treating FR-01.12/AC01 as fully bound** on the spawn-and-URL test alone.
  Rejected per Exception 1's own instruction: record BOTH halves, never let
  the provable half stand in as proof of the whole AC — the "at least one
  build section is complete" precondition shares AC02's no-seam reason and
  stays disclosed, not silently absorbed into a bound AC01.

## Result

**Updated post-review (external plan review + external code review both
surfaced corrections to this section — see the ADR's Findings tables for
full disposition):** 16 of 30 ACs bound (FR-01.01: 7/7, FR-01.05: 0/8,
FR-01.12: 4/9, FR-01.13: 5/6). 14 stay unbound with a concrete, evidenced
reason each: FR-01.05 AC01-AC08, all 8 — seam survey Exception 9 (no
`scripts/` implementation exists for any of them, including AC07: an
earlier draft tagged AC07 on the result-contract schema's required fields,
but a required field being present does not prove tests actually ran/passed
— external plan review, openai, HIGH — the marker was removed and the test
kept unmarked as a regression guard only); FR-01.12 AC01-AC03/AC07/AC09,
5 — seam survey Exception 1 (AC01 was briefly tagged as "half-bound" on the
spawn/URL test alone, but Exception 1's own instruction to "record BOTH
halves" means recording the no-seam precondition half too, which for a
conjunctive AC means staying unbound like AC02 — external code review,
openai HIGH + glm low); FR-01.13 AC06, 1 — no deterministic seam for
prose-quality. Re-derived directly from `shipwright_ac_coverage_baseline.json`
(85 -> 69 unbound repo-wide after both corrections), never copied from the
spec's AC-count text.
