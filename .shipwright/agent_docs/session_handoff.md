---
canon_generated: true
run_id: "iterate-2026-07-27-plan-phase-gates"
phase: "iterate"
reason: "ensure-current pre-merge refresh"
timestamp: "2026-07-27T08:43:16.422767+00:00"
---

# Session Handoff

> Auto-generated 2026-07-27 08:43:16 UTC

## Session Info

- **Session ID**: 1ea85a9d-f698-4336-8e01-ea2f4e2ae714
- **Timestamp**: 2026-07-27 08:43:16 UTC
- **Reason**: ensure-current pre-merge refresh

## Last Iterate

- **Run ID**: iterate-2026-07-27-plan-phase-gates
- **Date**: 2026-07-27T08:43:10.255493Z
- **Type**: change
- **Complexity**: medium
- **Branch**: iterate/plan-phase-gates
- **ADR**: iterate-2026-07-27-plan-phase-gates
- **Tests passed**: True
- **Spec**: .shipwright/planning/iterate/2026-07-27-plan-phase-gates.md

## Current Iterate Progress

- **Branch**: iterate/plan-phase-gates
- **Run ID**: `iterate-2026-07-27-plan-phase-gates`
- **Spec**: .shipwright/planning/iterate/2026-07-27-plan-phase-gates.md
- **Complexity**: medium
- **External Review Marker**: stale (predates spec (2026-07-27T07:17:11))

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

- **Branch**: iterate/plan-phase-gates
- **Last Commit**: dac19c82 Merge remote-tracking branch 'origin/main' into iterate/plan-phase-gates
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
- **Total work events**: 363
- **Last iterate**: change — iterate: the review gate stops being bypassable (fail-closed + fork review) (2026-07-27)
- **Resume**: `/shipwright-iterate` for next change, or `/shipwright-run` for new pipeline

## Recent Decisions

### ADR-328: Change history as a query over the event log, measured against what it replaced
- **Date:** 2026-07-20
- **Section:** Iterate → campaign S7 derived traceability
- **Run-ID:** iterate-2026-07-19-traceability-derived-view
- **Context:** Campaign decision D4 removed the 'Refined by <run_id>' prose from the requirements catalog because that history was said to live already in commits, the changelog and shipwright_events.jsonl. S6 executed the removal and left the catalog pointing at the event l
