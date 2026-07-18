---
canon_generated: true
run_id: "iterate-2026-07-18-fr-existence-gate"
phase: "iterate"
reason: "iterate: FR-existence gate — declared requirement ids must exist"
timestamp: "2026-07-18T16:11:11.897795+00:00"
---

# Session Handoff

> Auto-generated 2026-07-18 16:11:11 UTC

## Session Info

- **Session ID**: 29a26685-f650-4a1d-a048-e9730774350b
- **Timestamp**: 2026-07-18 16:11:11 UTC
- **Reason**: iterate: FR-existence gate — declared requirement ids must exist

## Last Iterate

- **Run ID**: iterate-2026-07-18-fr-existence-gate
- **Date**: 2026-07-18T16:11:06.125067Z
- **Type**: change
- **Complexity**: medium
- **Branch**: iterate/fr-existence-gate
- **ADR**: iterate-2026-07-18-fr-existence-gate
- **Tests passed**: True
- **Spec**: .shipwright/planning/iterate/2026-07-18-fr-existence-gate.md

## Current Iterate Progress

- **Branch**: iterate/fr-existence-gate
- **Spec**: .shipwright/planning/iterate/2026-07-18-fr-existence-gate.md
- **External Review Marker**: missing

### Mandatory replay on Resume

Before dispatching to the handoff's Remaining phase, run these if missing:
- Finalization (F0–F11) after all mandatory phases pass

## Legacy build state

- **Phase**: design
- **Current Split**: 01-adopted
- **Current Section**: adopted-baseline

- **Splits**: 0/1 complete
- **Sections**: 0/1 complete

## Git State

- **Branch**: iterate/fr-existence-gate
- **Last Commit**: 4fe2d680 feat(traceability): resolve tagged FR ids through the spec FR-Fold-Map (#397)
- **Uncommitted Changes**: Yes

## Config Files to Read

- `shipwright_run_config.json` — exists
- `shipwright_project_config.json` — exists
- `shipwright_plan_config.json` — exists
- `shipwright_build_config.json` — exists
- `shipwright_security_config.json` — exists
- `shipwright_compliance_config.json` — exists

## Last Events

| Event | Type | Source | Date |
|-------|------|--------|------|
| evt-9f5dc340 | grade_snapshot | — | 2026-07-18 |
| evt-3d1c18b7 | work_completed | iterate (iterate: FR-existence gate — declared requirement ids must exist) | 2026-07-18 |
| evt-7518638a | grade_snapshot | — | 2026-07-18 |
| evt-bcfaff37 | grade_snapshot | — | 2026-07-18 |
| evt-b58979bd | work_completed | iterate (iterate: suppress non-literal-import FP in the layer-coverage verifier) | 2026-07-18 |

## Recovery

- **Pipeline**: 1 phases completed
- **Total work events**: 327
- **Last iterate**: change — iterate: FR-existence gate — declared requirement ids must exist (2026-07-18)
- **Resume**: `/shipwright-iterate` for next change, or `/shipwright-run` for new pipeline

## Recent Decisions

### ADR-327: Per-test execution-evidence reader as the R1 coverage source
- **Date:** 2026-07-16
- **Section:** Iterate → TT-EV execution-evidence
- **Run-ID:** iterate-2026-07-15-execution-evidence
- **Context:** TT1 shipped the traceability manifest with per-test status/executed, but the only producer of the normalized evidence index was a hand-authored fixture. A static @FR tag proves nothing (Spec 11 R1 / unclosed G5): a skipped/never-run/filtered test would still satisfy a required layer.
- **Decis
