---
canon_generated: true
run_id: "iterate-2026-07-27-security-coverage-manifest"
phase: "iterate"
reason: "F11 refresh before merge"
timestamp: "2026-07-27T17:38:49.456380+00:00"
---

# Session Handoff

> Auto-generated 2026-07-27 17:38:49 UTC

## Session Info

- **Session ID**: 871b1865-c6ae-4724-a105-dc987ddca125
- **Timestamp**: 2026-07-27 17:38:49 UTC
- **Reason**: F11 refresh before merge

## Last Iterate

- **Run ID**: iterate-2026-07-27-run-unit-parallel-race
- **Date**: 2026-07-27T17:38:43.705219Z
- **Type**: bug
- **Complexity**: medium
- **Branch**: iterate/run-unit-parallel-race
- **ADR**: iterate-2026-07-27-run-unit-parallel-race
- **Tests passed**: True
- **Spec**: .shipwright/planning/iterate/iterate-2026-07-27-run-unit-parallel-race.md

## Current Iterate Progress

- **Branch**: iterate/security-coverage-manifest-part1
- **External Review Marker**: completed (external_review_state.json @ 2026-07-27T11:47:40)

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

- **Branch**: iterate/security-coverage-manifest-part1
- **Last Commit**: a0c23684 Merge remote-tracking branch 'origin/main' into iterate/security-coverage-manifest-part1
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
| evt-950798de | grade_snapshot | — | 2026-07-27 |
| evt-36d0f887 | work_completed | iterate (iterate: raise the PR-review diff cap, cut at a file boundary, name what went unreviewed) | 2026-07-27 |
| evt-ad7b51e0 | grade_snapshot | — | 2026-07-27 |
| evt-e3d8f519 | work_completed | iterate (iterate: an audit that checked nothing is not recorded) | 2026-07-27 |
| evt-024abc36 | grade_snapshot | — | 2026-07-27 |

## Recovery

- **Pipeline**: 1 phases completed
- **Total work events**: 383
- **Last iterate**: change — iterate: raise the PR-review diff cap, cut at a file boundary, name what went unreviewed (2026-07-27)
- **Resume**: `/shipwright-iterate` for next change, or `/shipwright-run` for new pipeline

## Recent Decisions

### ADR-328: Change history as a query over the event log, measured against what it replaced
- **Date:** 2026-07-20
- **Section:** Iterate → campaign S7 derived traceability
- **Run-ID:** iterate-2026-07-19-traceability-derived-view
- **Context:** Campaign decision D4 removed the 'Refined by <run_id>' prose from the requirements catalog because that history was said to live already in commits, the changelog and shipwright_events.jsonl. S6 executed the removal and left the catalog pointing at the event l
