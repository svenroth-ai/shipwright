---
canon_generated: true
run_id: "iterate-2026-07-27-adopt-derived-catalogue"
phase: "iterate"
reason: "iterate: the derived requirements catalogue announces itself"
timestamp: "2026-07-27T11:51:44.632826+00:00"
---

# Session Handoff

> Auto-generated 2026-07-27 11:51:44 UTC

## Session Info

- **Session ID**: 98053cc9-0f7c-4be8-b1cc-8b5d8b25d84b
- **Timestamp**: 2026-07-27 11:51:44 UTC
- **Reason**: iterate: the derived requirements catalogue announces itself

## Last Iterate

- **Run ID**: iterate-2026-07-27-adopt-derived-catalogue
- **Date**: 2026-07-27T11:51:38.364103Z
- **Type**: feature
- **Complexity**: medium
- **Branch**: iterate/adopt-derived-catalogue
- **ADR**: iterate-2026-07-27-adopt-derived-catalogue
- **Tests passed**: True
- **Spec**: .shipwright/planning/iterate/2026-07-27-adopt-derived-catalogue.md

## Current Iterate Progress

- **Branch**: iterate/adopt-derived-catalogue
- **Run ID**: iterate-2026-07-27-adopt-derived-catalogue
- **Spec**: .shipwright/planning/iterate/2026-07-27-adopt-derived-catalogue.md
- **Complexity**: medium
- **External Review Marker**: completed (external_review_state.json @ 2026-07-27T11:49:21)

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

- **Branch**: iterate/adopt-derived-catalogue
- **Last Commit**: b654dedd chore(triage): sweep 6 outbox append(s) into branch
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
| evt-4ab23c76 | grade_snapshot | — | 2026-07-27 |
| evt-cdd626e1 | work_completed | iterate (iterate: the derived requirements catalogue announces itself) | 2026-07-27 |
| evt-64bc7af0 | grade_snapshot | — | 2026-07-27 |
| evt-19f53577 | grade_snapshot | — | 2026-07-27 |
| evt-78684181 | work_completed | iterate (iterate: the review gate stops being bypassable (fail-closed + fork review)) | 2026-07-27 |

## Recovery

- **Pipeline**: 1 phases completed
- **Total work events**: 366
- **Last iterate**: change — iterate: the derived requirements catalogue announces itself (2026-07-27)
- **Resume**: `/shipwright-iterate` for next change, or `/shipwright-run` for new pipeline

## Recent Decisions

### ADR-328: Change history as a query over the event log, measured against what it replaced
- **Date:** 2026-07-20
- **Section:** Iterate → campaign S7 derived traceability
- **Run-ID:** iterate-2026-07-19-traceability-derived-view
- **Context:** Campaign decision D4 removed the 'Refined by <run_id>' prose from the requirements catalog because that history was said to live already in commits, the changelog and shipwright_events.jsonl. S6 executed the removal and left the catalog pointing at the event l
