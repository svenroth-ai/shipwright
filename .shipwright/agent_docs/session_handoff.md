# Session Handoff

> Auto-generated 2026-07-20 12:51:25 UTC

## Session Info

- **Session ID**: 85c973ff-4812-4db0-acc1-935ed32ee51b
- **Timestamp**: 2026-07-20 12:51:25 UTC
- **Reason**: context compaction

## Last Iterate

- **Run ID**: iterate-2026-07-19-requirements-merge-catalog
- **Date**: 2026-07-20T11:22:18.961613Z
- **Type**: change
- **Complexity**: medium
- **Branch**: iterate/requirements-merge-catalog
- **ADR**: iterate-2026-07-19-requirements-merge-catalog
- **Tests passed**: True
- **Spec**: .shipwright/planning/01-adopted/spec.md

## Current Iterate Progress

- **Branch**: iterate/requirements-merge-catalog
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

- **Branch**: iterate/requirements-merge-catalog
- **Last Commit**: b9d54ec0 refactor(requirements): one catalog, stated once in plain language (campaign S6)
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
| evt-1e9a1554 | grade_snapshot | — | 2026-07-20 |
| evt-efec7e37 | grade_snapshot | — | 2026-07-20 |
| evt-5e0495a3 | grade_snapshot | — | 2026-07-20 |
| evt-3e0e8a82 | grade_snapshot | — | 2026-07-20 |
| evt-9b2aca55 | grade_snapshot | — | 2026-07-20 |

## Recovery

- **Pipeline**: 1 phases completed
- **Total work events**: 341
- **Last iterate**: change — iterate: merge the requirements into one catalog (campaign S6) (2026-07-20)
- **Resume**: `/shipwright-iterate` for next change, or `/shipwright-run` for new pipeline

## Recent Decisions

### ADR-327: Per-test execution-evidence reader as the R1 coverage source
- **Date:** 2026-07-16
- **Section:** Iterate → TT-EV execution-evidence
- **Run-ID:** iterate-2026-07-15-execution-evidence
- **Context:** TT1 shipped the traceability manifest with per-test status/executed, but the only producer of the normalized evidence index was a hand-authored fixture. A static @FR tag proves nothing (Spec 11 R1 / unclosed G5): a skipped/never-run/filtered test would still satisfy a required layer.
- **Decis
