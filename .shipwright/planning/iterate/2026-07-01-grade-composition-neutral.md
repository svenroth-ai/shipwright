# Iterate Spec — Make the Control Grade composition-neutral (drop the FR-tag-decline gate)

- **Run ID:** `iterate-2026-07-01-grade-composition-neutral`
- **Intent:** CHANGE
- **Complexity:** medium (core metric — compliance grading logic)
- **Spec Impact:** MODIFY — FR-01.10 (`/shipwright-compliance` Control Grade behavior)

## Problem

The Control Grade's honesty gate penalised and capped on a **self-relative FR-tag
decline** (recent strict FR-tag rate below the repo's own all-time rate): it
depressed the requirement-traceability dimension (`apply_traceability_penalty`)
and capped the headline at B (`apply_verdict_gate` branch (a)). This conflates
**workload composition** (feature vs. maintenance mix) with **control**. A repo
doing a correct, honest maintenance/hardening sprint (few new FR-tags, all
properly classified no-FR) is fully in control, yet the grade dropped.

Empirically (checked before implementing, on current data):
- The gate would have **fired at 94 %** (194/207) of the monorepo's history; the
  recent-30 FR-tag rate swung **0 %–87 %** purely from work mix.
- The **WebUI** was capped at **B** with **all 7 dimensions green** (42/42 FRs
  covered, 0/23 unreconciled, 0 high/critical) purely because its FR-tag rate of
  **57 %** was **2 pp** below its own 59 % all-time baseline.
- From the current monorepo A-state, just **18** honest no-FR events would re-trigger the cap.

## Goal

Composition is grade-neutral. Control = "is every requirement's state known and
current, and is every change honestly attributed" — carried by requirement
**coverage** + change **reconciliation** (both composition-independent) and the
write-time **FR-gate** (which already hard-blocks a behavior-affecting change that
omits its FR). The feature-vs-maintenance *rate* no longer caps or lowers the grade.

## Change

- `_grade_gate.py`: remove `apply_traceability_penalty`, `trace_decline_severity`,
  `TRACE_DECLINE_MAX_PENALTY`, `_pct`, and `apply_verdict_gate` **branch (a)**.
  Keep the dark-expected-control cap and the broken-pillar (F) cap.
- `control_grade.py`: drop the penalty call + import; requirement dimension is now
  purely coverage + classification-completeness.
- `_grade_types.py`: remove the now-dead `GradeInputs.fr_tag_recent_pct/all_pct/window`.
- `_control_block.py`: stop lighting those fields; drop the unused `fr_tag_trend` import.
- `_traceability.py` `render_traced_row`: **informational** row (INFO, never WARN).
- Docs/spec: `spec.md` FR-01.10 AC, `guide.md`, `docs/hooks-and-pipeline.md`,
  `architecture.md` (component entry) updated to the composition-neutral model.
- Tests: `test_grade_gate.py`, `test_traceability.py`, `test_reconciliation.py`
  rewritten to the new contract.

## Affected Boundaries

- Compliance grading kernel (`_grade_gate`, `control_grade`, `_grade_types`) +
  adapter (`_control_block`) + dashboard row (`_traceability`). No data-format
  change; `GradeInputs` loses 3 fields (internal, not serialized).
- Cross-repo: the same plugin logic grades the WebUI — after this merges +
  `update-marketplace.sh`, a WebUI re-grade lifts it B→A (separate WebUI iterate).

## Confidence Calibration

- **Boundaries touched:** compliance grading kernel + adapter + dashboard row;
  FR-01.10 spec AC; guide/hooks/architecture docs. Plugin **source** change →
  requires `update-marketplace.sh` post-merge.
- **Empirical probes run:**
  1. **Pre-change historical analysis** (real data): decline gate fired 94 % of
     monorepo history; recent-30 swung 0–87 %; WebUI B at 57 % vs 59 %.
  2. **F0 full suite:** 4964 passed, 0 failed (compliance 909, shared 3624+196+61,
     integration 174); repo-wide ruff clean.
  3. **End-to-end producer probe** (real adapter + real scorer): baseline **A
     (100/100)**; after a 25-event honest maintenance sprint (recent FR-tag **3 %
     vs 19 %**) the grade is **still A (100/100)** — `composition-neutral = True`;
     the old gate would have capped it to B. Row renders **INFO**.
  4. **Adversarial code review** (fresh-context opus): checks for stale readers of
     the removed fields, dead imports, tests asserting old behavior, and CI risk.
  5. **Post-finalize producer regen:** dashboard grade A, row INFO, no "declining"
     language — confirmed at F5b.
- **Test Completeness Ledger:**

  | # | Behavior | Status | Evidence |
  |---|----------|--------|----------|
  | 1 | Composition (FR-tag decline) no longer penalises the requirement dimension | tested | probe 3 (sprint → A); `test_grade_gate::TestPerfectRepoIsA` + `test_low_requirement_traceability_is_a_gap_not_an_F` |
  | 2 | Composition no longer caps the headline verdict | tested | probe 3 (recent 3% < all 19% → still A); `test_grade_gate` (no "Capped" on perfect repo) |
  | 3 | Dark-expected-control cap still works (B + "verification incomplete") | tested | `test_grade_gate::TestVerdictGateDarkExpected` |
  | 4 | Broken-pillar cap still works (F) | tested | `test_grade_gate::TestVerdictGateBrokenPillar` |
  | 5 | Dashboard row is INFO, never WARN/"frozen" | tested | `test_traceability::TestRenderTracedRow` (4 cases incl. 0% recent) |
  | 6 | No dead code / no stale reader of removed fields/functions | tested | repo-wide ruff clean; F0 4964 passed; adversarial review (probe 4) |

  0 testable-but-untested · 0 untestable rows · enumeration covers the change.
- **Confidence-pattern check:** asymptote (depth) — verified against the **real
  producer** end-to-end, not only unit tests, with an actual maintenance-sprint
  scenario. Coverage (breadth) — kernel + adapter + dashboard row + full-suite
  regression + fresh-context adversarial review. Integration composition — n/a
  (no `cross_component` machinery touched).
