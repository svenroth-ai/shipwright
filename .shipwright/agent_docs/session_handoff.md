---
canon_generated: true
run_id: "iterate-2026-07-28-docs-placement-rule"
phase: "iterate"
reason: "iterate: docs/ placement rule + remove one generated artifact and five finished records"
timestamp: "2026-07-28T12:18:50.089137+00:00"
---

# Session Handoff

> Auto-generated 2026-07-28 12:18:50 UTC

## Session Info

- **Session ID**: 7c6c7b07-d3a2-4c91-ba4e-fab3535b5067
- **Timestamp**: 2026-07-28 12:18:50 UTC
- **Reason**: iterate: docs/ placement rule + remove one generated artifact and five finished records

## Last Iterate

- **Run ID**: iterate-2026-07-28-docs-placement-rule
- **Date**: 2026-07-28T12:18:44.151571Z
- **Type**: change
- **Complexity**: medium
- **Branch**: iterate/docs-placement-rule
- **ADR**: iterate-2026-07-28-docs-placement-rule
- **Tests passed**: True
- **Spec**: .shipwright/planning/iterate/iterate-2026-07-28-docs-placement-rule.md

## Current Iterate Progress

- **Branch**: iterate/docs-placement-rule
- **Run ID**: iterate-2026-07-28-docs-placement-rule
- **Spec**: .shipwright/planning/iterate/iterate-2026-07-28-docs-placement-rule.md
- **Complexity**: medium · **spec_impact:** none · **affected_frs:** [] ·
- **External Review Marker**: completed (external_review_state.json @ 2026-07-28T11:58:04)

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

- **Branch**: iterate/docs-placement-rule
- **Last Commit**: 7ec426a2 chore(triage): sweep 54 outbox append(s) into branch
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
| evt-003a4ccb | grade_snapshot | — | 2026-07-28 |
| evt-a25fc820 | work_completed | iterate (iterate: docs/ placement rule + remove one generated artifact and five finished records) | 2026-07-28 |
| evt-7963d51e | grade_snapshot | — | 2026-07-28 |
| evt-2df150c5 | work_completed | iterate (Make a conditional session policy gating subagents a question asked before Stage 1 rather than a silent not_run at F11, and define what a real blocker is.) | 2026-07-28 |
| evt-5f7e67f6 | grade_snapshot | — | 2026-07-28 |

## Recovery

- **Pipeline**: 1 phases completed
- **Total work events**: 400
- **Last iterate**: change — iterate: docs/ placement rule + remove one generated artifact and five finished records (2026-07-28)
- **Resume**: `/shipwright-iterate` for next change, or `/shipwright-run` for new pipeline

## Recent Decisions

### ADR-328: Change history as a query over the event log, measured against what it replaced
- **Date:** 2026-07-20
- **Section:** Iterate → campaign S7 derived traceability
- **Run-ID:** iterate-2026-07-19-traceability-derived-view
- **Context:** Campaign decision D4 removed the 'Refined by <run_id>' prose from the requirements catalog because that history was said to live already in commits, the changelog and shipwright_events.jsonl. S6 executed the removal and left the catalog pointing at the event l
