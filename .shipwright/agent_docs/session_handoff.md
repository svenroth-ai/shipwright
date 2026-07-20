---
canon_generated: true
run_id: "iterate-2026-07-20-converge-table-shape"
phase: "iterate"
reason: "iterate finalization"
timestamp: "2026-07-20T09:49:32.816776+00:00"
---

# Session Handoff

> Auto-generated 2026-07-20 09:49:32 UTC

## Session Info

- **Session ID**: 85c973ff-4812-4db0-acc1-935ed32ee51b
- **Timestamp**: 2026-07-20 09:49:32 UTC
- **Reason**: iterate finalization

## Last Iterate

- **Run ID**: iterate-2026-07-20-converge-table-shape
- **Date**: 2026-07-20T07:21:06.009070Z
- **Type**: change
- **Complexity**: medium
- **Branch**: iterate/converge-table-shape
- **ADR**: iterate-2026-07-20-converge-table-shape
- **Tests passed**: True
- **Spec**: .shipwright/planning/iterate/iterate-2026-07-20-converge-table-shape.md

## Current Iterate Progress

- **Branch**: iterate/converge-table-shape
- **Spec**: .shipwright/planning/iterate/iterate-2026-07-20-converge-table-shape.md
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

- **Branch**: iterate/converge-table-shape
- **Last Commit**: e6b0c5a5 refactor(requirements): one FR-table shape from both generators (campaign S5)
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
| evt-ec9fc299 | grade_snapshot | — | 2026-07-20 |
| evt-7d38f305 | grade_snapshot | — | 2026-07-20 |
| evt-901afec3 | grade_snapshot | — | 2026-07-20 |
| evt-1024c658 | grade_snapshot | — | 2026-07-20 |
| evt-8ebeed1d | grade_snapshot | — | 2026-07-20 |

## Recovery

- **Pipeline**: 1 phases completed
- **Total work events**: 340
- **Last iterate**: change — iterate: converge the FR table shape (campaign S5) (2026-07-20)
- **Resume**: `/shipwright-iterate` for next change, or `/shipwright-run` for new pipeline

## Recent Decisions

### ADR-327: Per-test execution-evidence reader as the R1 coverage source
- **Date:** 2026-07-16
- **Section:** Iterate → TT-EV execution-evidence
- **Run-ID:** iterate-2026-07-15-execution-evidence
- **Context:** TT1 shipped the traceability manifest with per-test status/executed, but the only producer of the normalized evidence index was a hand-authored fixture. A static @FR tag proves nothing (Spec 11 R1 / unclosed G5): a skipped/never-run/filtered test would still satisfy a required layer.
- **Decis
