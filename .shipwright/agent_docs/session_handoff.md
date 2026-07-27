---
canon_generated: true
run_id: "iterate-2026-07-27-rollback-uses-target-ref"
phase: "iterate"
reason: "F11 re-refresh: origin/main moved again (round 4)"
timestamp: "2026-07-27T09:08:48.846142+00:00"
---

# Session Handoff

> Auto-generated 2026-07-27 09:08:48 UTC

## Session Info

- **Session ID**: 13f13377-3431-4445-b501-bc754d78d6d3
- **Timestamp**: 2026-07-27 09:08:48 UTC
- **Reason**: F11 re-refresh: origin/main moved again (round 4)

## Last Iterate

- **Run ID**: iterate-2026-07-27-artifact-state-stamping
- **Date**: 2026-07-27T09:08:42.675204Z
- **Type**: feature
- **Complexity**: medium
- **Branch**: iterate/artifact-state-stamping
- **ADR**: iterate-2026-07-27-artifact-state-stamping
- **Tests passed**: True
- **Spec**: .shipwright/planning/iterate/2026-07-27-artifact-state-stamping.md

## Current Iterate Progress

- **Branch**: iterate/rollback-uses-target-ref
- **Run ID**: iterate-2026-07-27-rollback-uses-target-ref
- **Spec**: .shipwright/planning/iterate/iterate-2026-07-27-rollback-uses-target-ref.md
- **Complexity**: medium
- **External Review Marker**: stale (predates spec (2026-07-27T07:16:58))

### Mandatory replay on Resume

Before dispatching to the handoff's Remaining phase, run these if missing:
- Step 4 — External LLM Review (marker missing/stale)
- Finalization (F0–F11) after all mandatory phases pass

## Legacy build state

- **Phase**: design
- **Current Split**: 01-adopted
- **Current Section**: adopted-baseline

- **Splits**: 0/1 complete
- **Sections**: 0/1 complete

## Git State

- **Branch**: iterate/rollback-uses-target-ref
- **Last Commit**: f5ea24a5 Merge remote-tracking branch 'origin/main' into iterate/rollback-uses-target-ref
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
| evt-64bc7af0 | grade_snapshot | — | 2026-07-27 |
| evt-19f53577 | grade_snapshot | — | 2026-07-27 |
| evt-78684181 | work_completed | iterate (iterate: the review gate stops being bypassable (fail-closed + fork review)) | 2026-07-27 |
| evt-c880344a | grade_snapshot | — | 2026-07-27 |
| evt-4794dcc1 | work_completed | iterate (iterate: phase-gate override leaves evidence; handoff renders phase status) | 2026-07-27 |

## Recovery

- **Pipeline**: 1 phases completed
- **Total work events**: 365
- **Last iterate**: change — iterate: the review gate stops being bypassable (fail-closed + fork review) (2026-07-27)
- **Resume**: `/shipwright-iterate` for next change, or `/shipwright-run` for new pipeline

## Recent Decisions

### ADR-328: Change history as a query over the event log, measured against what it replaced
- **Date:** 2026-07-20
- **Section:** Iterate → campaign S7 derived traceability
- **Run-ID:** iterate-2026-07-19-traceability-derived-view
- **Context:** Campaign decision D4 removed the 'Refined by <run_id>' prose from the requirements catalog because that history was said to live already in commits, the changelog and shipwright_events.jsonl. S6 executed the removal and left the catalog pointing at the event l
