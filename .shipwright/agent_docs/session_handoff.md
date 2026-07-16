---
canon_generated: true
run_id: "iterate-2026-07-15-required-layers-on-frs"
phase: "iterate"
reason: "iterate: required_layers on FRs (TT3)"
timestamp: "2026-07-16T06:19:26.145657+00:00"
---

# Session Handoff

> Auto-generated 2026-07-16 06:19:26 UTC

## Session Info

- **Session ID**: a69abb9e-d21a-40a1-846b-13913cca2b09
- **Timestamp**: 2026-07-16 06:19:26 UTC
- **Reason**: iterate: required_layers on FRs (TT3)

## Last Iterate

- **Run ID**: iterate-2026-07-15-required-layers-on-frs
- **Date**: 2026-07-16T05:37:03.123238Z
- **Type**: feature
- **Complexity**: medium
- **Branch**: iterate/campaign-TT3-required-layers-on-frs
- **ADR**: iterate-2026-07-15-required-layers-on-frs
- **Tests passed**: True
- **Spec**: .shipwright/planning/iterate/iterate-2026-07-15-required-layers-on-frs.md

## Current Iterate Progress

- **Branch**: iterate/campaign-TT3-required-layers-on-frs
- **External Review Marker**: completed (external_review_state.json @ 2026-07-16T05:34:21)

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

- **Branch**: iterate/campaign-TT3-required-layers-on-frs
- **Last Commit**: 73baad07 feat(traceability): declare required_layers per FR + adopt surface-inference (TT3)
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
| evt-52bbc0b4 | grade_snapshot | — | 2026-07-16 |
| evt-05a832b4 | grade_snapshot | — | 2026-07-16 |
| evt-34535c2f | work_completed | iterate (FR Layers column + adopt surface-inference + (inferred) advisory-provenance marker (TT3)) | 2026-07-16 |
| evt-c055f554 | grade_snapshot | — | 2026-07-15 |
| evt-efd3417b | grade_snapshot | — | 2026-07-15 |

## Recovery

- **Pipeline**: 1 phases completed
- **Total work events**: 309
- **Last iterate**: feature — FR Layers column + adopt surface-inference + (inferred) advisory-provenance marker (TT3) (2026-07-16)
- **Resume**: `/shipwright-iterate` for next change, or `/shipwright-run` for new pipeline

## Recent Decisions

### ADR-327: Per-test execution-evidence reader as the R1 coverage source
- **Date:** 2026-07-16
- **Section:** Iterate → TT-EV execution-evidence
- **Run-ID:** iterate-2026-07-15-execution-evidence
- **Context:** TT1 shipped the traceability manifest with per-test status/executed, but the only producer of the normalized evidence index was a hand-authored fixture. A static @FR tag proves nothing (Spec 11 R1 / unclosed G5): a skipped/never-run/filtered test would still satisfy a required layer.
- **Decis
