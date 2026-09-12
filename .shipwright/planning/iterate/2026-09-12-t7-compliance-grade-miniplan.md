# Mini-Plan: t7 — AC-proving tests for FR-01.10 (/shipwright-compliance) + FR-01.18 (/shipwright-grade)

Campaign: `req3-05-test-backfill-mono`. Run-ID: `iterate-2026-09-12-t7-compliance-grade`.
Branch: `iterate/campaign-req3-05-test-backfill-mono-t7`.

## Problem statement

22 ACs (`FR-01.10` AC01–AC14, `FR-01.18` AC01–AC08) are listed `unbound` in
`shipwright_ac_coverage_baseline.json`: no `@pytest.mark.covers` test binds them.
Declared test roots — cited verbatim from the t0 seam survey's Master mapping
table (`.shipwright/planning/iterate/2026-09-11-req3-05-seam-survey.md`, the
`FR-01.10` and `FR-01.18` rows):

> `FR-01.10` | `/shipwright-compliance` | 14 / 14 | `plugins/shipwright-compliance/tests`
> | `test_audit_*` family (Group A–I audits) — pick the audit group file matching the
> AC's dimension; `test_rtm_generator.py` for traceability ACs | none yet | t7
>
> `FR-01.18` | `/shipwright-grade` | 8 / 8 | `plugins/shipwright-grade/tests`
> | `test_grade_cli.py` (real CLI entry point), `test_authoritative.py`,
> `test_negative_fixtures.py`, `test_network_policy.py` (consent-gating ACs) | none yet | t7

## Approach

1. Read every AC's text in `.shipwright/planning/01-adopted/spec.md` FR-01.10
   (lines 652-727) and FR-01.18 (lines 1218-1251) verbatim, rather than trusting
   any paraphrase.
2. For each AC, find the REAL enforcing production code path in the declared
   root's own plugin (`plugins/shipwright-compliance/scripts/audit/*`,
   `scripts/lib/*` for compliance; `plugins/shipwright-grade/scripts/lib/*` for
   grade) and locate an EXISTING test that already exercises it end-to-end —
   never a renderer-only or wrapper-only proxy. Where a test proves only half a
   conjunctive AC, pair a second existing test for the other half rather than
   writing a new one, per the campaign's "no new harness where a fitting one
   exists" rule.
3. Tag with `@pytest.mark.covers("FR-0X.YY/ACnn")` — stacking a second
   decorator where a test already carries an FR-01.02/FR-01.16 tag from t6
   (`test_retired_fr_number_must_not_be_reused` also proves FR-01.10/AC14's
   "reuse of a retired number" clause).
4. Where an AC's only full seam sits in a test root outside this unit's two
   declared roots, follow the t5/t6 precedent: flag it (do not self-authorize),
   but the campaign owner has standing pre-approval for this recurring
   pattern (2026-09-12) — cite and proceed rather than re-asking. FR-01.10/AC03's
   second clause ("a recorded test run names the code version, read from the
   project") is proven by `shared/tests/test_stamp_test_results.py`
   (`stamp_test_results.py`, "call site 1 of the artifact-state stamp, card
   trg-4d5b6a56, FR-01.10" — the module's own docstring names this FR), a
   pre-existing, already-passing suite; two of its tests are tagged.
5. For genuinely un-provable ACs, record unbound with a concrete, evidenced
   reason rather than forcing a proxy binding:
   - **AC04** — a real, end-to-end seam was found and used instead:
     `integration-tests/test_adopt_evidence_stamp_e2e.py::test_a_repository_with_no_commits_can_still_be_onboarded`
     proves the full conjunction (a commitless repo still onboards; the
     evidence documents committed name no base; `--verify-commit` genuinely
     rejects a no-`base=` banner). Initially assumed no seam spanned both
     plugins; External Plan Review (OpenAI, medium) asked for an actual
     search rather than an assumed gap, and the search found this test — see
     the ADR's External-Plan-Review-Findings table, finding #4. AC04 is
     bound, not unbound.
   - **AC06** ("reported together with a suggested command to fix it, without
     failing the audit") maps to Group D's D5 check (`_check_d5`,
     `plugins/shipwright-compliance/scripts/audit/group_d.py`), which DOES
     carry a `suggested_iterate_cmd` on failure — but D5 sets
     `status="fail"`, which flips `AuditReport.any_fail` and the audit's exit
     code (verified by reading `run_audit.py:122` and `audit_detector.py`'s
     `any_fail` property). This contradicts the AC's own "without failing the
     audit" clause. Recorded as a genuine spec-vs-implementation discrepancy
     rather than forced onto a test that would misrepresent what the code
     does — filed as triage card `trg-6bda0dbb` (External Plan Review,
     OpenAI/GLM medium: a durable card, not only `result.json.unresolved_flags`).
6. Regenerate `shipwright_ac_coverage_baseline.json` from a freshly
   regenerated (but NOT committed — CI's own "Check traceability manifest
   against a fresh regeneration" step regenerates
   `.shipwright/compliance/test-traceability.json` in place from real JUnit
   output before the AC-coverage gate reads it, per `.github/workflows/ci.yml`
   — committing a locally-regenerated copy here would misrepresent it as
   built from this run's real JUnit reports) `.shipwright/compliance/test-traceability.json`,
   via `check_ac_coverage_ratchet.py --write`, mirroring t3–t6's identical
   precedent.

## Alternatives considered

- **Writing brand-new tests for every AC from scratch**, ignoring the dense
  existing `test_audit_*` / `test_traceability.py` / grade-plugin suites that
  already exercise the exact production code paths these ACs describe.
  Rejected: both plugins already have thorough, well-named test coverage for
  their own real behaviour — the gap was tagging, not testing. Two new
  functions were needed anyway (none, in this unit — every AC found an
  existing, real, passing test to tag).
- **Binding AC04/AC06 to a weak proxy** to reach "22 of 22 bound". Rejected
  outright by the binding constraint on this sub-iterate's own spec: "A test
  shaped around the implementation it was written against does not count and
  will be rejected in review." AC06 in particular would require asserting the
  audit does NOT fail when the real code DOES fail it — that is not proving
  the AC, it is fabricating a passing test around a false premise.
- **Self-authorizing the 3rd test root** `shared/tests/test_stamp_test_results.py`
  needs for AC03's second clause, without flagging it. Rejected: mirrors
  t5/t6's own precedent of flagging rather than deciding unilaterally, even
  though the campaign owner's standing pre-approval means this does not block
  finishing.

## Result

21 of 22 ACs bound (13 of FR-01.10's 14; all 8 of FR-01.18's 8). Only AC06
remains unbound, with a concrete, evidenced reason (a real
spec-vs-implementation discrepancy in Group D's D5 check — see below). AC04
was initially recorded unbound in this plan's first draft on the assumption
no seam spans both plugins; External Plan Review (OpenAI, medium) asked for
an actual search rather than an assumed gap, and the search found a real
end-to-end seam in `integration-tests/`. Re-derived directly from
`shipwright_ac_coverage_baseline.json` (106 → 85 unbound repo-wide), never
copied from the spec's AC-count text. Full per-AC disposition table and the
External-Plan-Review-Findings table (all 11 findings dispositioned):
`.shipwright/planning/adr/iterate-2026-09-12-t7-compliance-grade-ac-bindings.md`.
