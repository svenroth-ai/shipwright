# Iterate Spec: Compliance dashboard — readable verdict + latest-suite + inline audit

**Run ID:** iterate-2026-06-27-compliance-control-grade
**Date:** 2026-06-27
**Intent:** feature (AR-01) + bug (AR-02, AR-03)
**Complexity:** medium (classifier: medium, conf 0.7, no risk flags)
**Spec Impact:** NONE — compliance-artifact rendering/scoring; no product FR.

## What this iterate does
1. **AR-01** — a new pure, repo-agnostic `lib/control_grade.py` computes a deterministic,
   importance-weighted control-posture grade (A–F) and renders a Control Verdict + Control Grade block
   atop `dashboard.md`. Methodology *in Anlehnung an* OpenSSF Scorecard: weighted average over the
   *measurable* dimensions; a dimension that can't be evaluated is `n/a` and **excluded from the
   denominator** (never silently 0); all-n/a → "Not Gradeable", never an unearned `F`. Each dimension
   names the recognized standard it follows.
2. **AR-02** — a shared `lib/_latest_suite.py` resolver makes the dashboard + test-evidence "latest
   tests" read the last event that actually ran a full suite, so a trailing run of doc/tooling changes
   no longer surfaces a `0/0` headline.
3. **AR-03** — inline the consistency-audit summary on the dashboard instead of linking the gitignored
   `audit-report.md` (which 404s on public GitHub).

> Design rationale, standards-anchoring research, and the follow-up roadmap live in the internal
> planning Spec (not tracked).

## Acceptance Criteria
- **AC-1:** the grade is computed deterministically from the rubric; same inputs → same grade; n/a
  dimensions excluded from the weighted denominator.
- **AC-2:** the dashboard renders, above Quality Indicators, a plain-language Verdict (mapped to the band
  table, no free-text drift) + Control Grade + score + top 1–3 fixable reasons + a `Verified from:` line.
- **AC-3:** the block renders for both adopted and greenfield projects; unmeasurable dimensions show
  `n/a`, not 0.
- **AC-4:** the "All unit tests passing" headline reads the latest full suite; `0/0` is impossible when
  the log holds a prior suite; an accurate "+N changes since" note.
- **AC-5:** test-evidence's latest-tests summary uses the same shared resolver.
- **AC-6:** no tracked artifact links to a gitignored path; an inline Consistency Audit summary is sourced
  from `audit-report.json`, with a graceful note when it is absent.
- **AC-7:** full plugin test suite green; no file > 300 LOC; lint clean.

## Affected files
- NEW `plugins/shipwright-compliance/scripts/lib/control_grade.py` (pure scorer)
- NEW `plugins/shipwright-compliance/scripts/lib/_control_block.py` (adapter + render)
- NEW `plugins/shipwright-compliance/scripts/lib/_latest_suite.py` (shared resolver)
- `plugins/shipwright-compliance/scripts/lib/compliance_report.py` (wire AR-01/02/03; drop dead link)
- `plugins/shipwright-compliance/scripts/lib/test_evidence.py` (AR-02 shared resolver)
- NEW/updated tests under `plugins/shipwright-compliance/tests/`
- `docs/guide.md` (§4.10 dashboard description)

## Verification (the inbound analysis was checked against the tree before building)
The external analysis was produced outside this repo, so every claim was verified against the code: the
three issues reproduce. Corrections were applied where it under-specified — notably that "latest full
suite" requires a deterministic resolver because the event log carries no full-suite flag, and that
dimensions which can't be honestly computed yet must render `n/a` rather than 0.

## Confidence Calibration
- **Boundaries touched:** reads `shipwright_events.jsonl` (via collectors), `audit-report.json`,
  `shipwright_bloat_baseline.json`; writes `dashboard.md`, `test-evidence.md`. `json.load` is read-only
  over existing artifacts (no new IO contract) → no new round-trip boundary.
- **Empirical probes run:** (1) rendered the real dashboard → Control Verdict block present, grade
  computed deterministically, unmeasurable dimensions shown `n/a` and excluded from the denominator;
  (2) the AR-02 headline reads the latest full suite (not the last event), so no `0/0`; (3) the AR-03
  inline Consistency Audit summary is populated from `audit-report.json`, dead link absent; (4)
  determinism: identical inputs → identical score (asserted).
- **Test Completeness Ledger:**

  | Behavior | Status | Evidence |
  |---|---|---|
  | Weighted aggregate, all-green → A | tested | `test_all_green_is_A` |
  | Band thresholds inclusive (90/80/70/50) | tested | `test_band_thresholds_are_inclusive` |
  | n/a excluded from denominator | tested | `TestNaExclusion` (3) |
  | All-n/a → Not Gradeable, never F | tested | `test_all_na_is_not_gradeable_never_F` |
  | Determinism (same inputs → same grade) | tested | `test_same_inputs_same_grade` |
  | Verdict maps to band (no free-text drift) | tested | `test_verdict_maps_to_band_no_freetext` |
  | Display int never contradicts letter band | tested | `test_displayed_int_*`, `test_floored_score_*` |
  | Garbage inputs stay in [0,100] | tested | `test_garbage_inputs_stay_in_range` |
  | AR-02 resolver (latest full suite, ts-ordered) | tested | `TestLatestSuiteResolver` (3) |
  | AR-02 dashboard headline = latest full suite | tested | `test_failing_*`, `test_passing_*` |
  | AR-02 test-evidence summary uses shared resolver | tested | `test_test_evidence.py` green |
  | AR-03 no dead link + inline audit summary | tested | `test_audit_report_not_linked_but_inlined` |
  - 0 testable-but-untested behaviors.
- **Confidence-pattern check:** depth via adversarial code review + the real-data probe; breadth across
  all dimensions + both AR-02 sites + the AR-03 fallback. No `cross_component` machinery touched (pure
  renderer/scorer) → no integration-composition row required.
