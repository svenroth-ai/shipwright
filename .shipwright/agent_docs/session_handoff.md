---
canon_generated: true
run_id: "iterate-2026-07-27-pytest-root-composition"
phase: "iterate"
reason: "iterate: refuse a multi-root pytest session instead of failing 21 unrelated tests"
timestamp: "2026-07-27T17:19:57.990788+00:00"
---

# Session Handoff

> Auto-generated 2026-07-27 17:19:57 UTC

## Session Info

- **Session ID**: 2a2ccc95-e7ec-4ca6-bcdb-601ae9e9b002
- **Timestamp**: 2026-07-27 17:19:57 UTC
- **Reason**: iterate: refuse a multi-root pytest session instead of failing 21 unrelated tests

## Last Iterate

- **Run ID**: iterate-2026-07-27-pytest-root-composition
- **Date**: 2026-07-27T17:19:50.695876Z
- **Type**: bug
- **Complexity**: medium
- **Branch**: iterate/pytest-root-composition
- **ADR**: iterate-2026-07-27-pytest-root-composition
- **Tests passed**: True
- **Spec**: .shipwright/planning/iterate/iterate-2026-07-27-pytest-root-composition.md

## Current Iterate Progress

- **Branch**: iterate/pytest-root-composition
- **Run ID**: `iterate-2026-07-27-pytest-root-composition`
- **Spec**: .shipwright/planning/iterate/iterate-2026-07-27-pytest-root-composition.md
- **Complexity**: medium
- **External Review Marker**: completed (external_review_state.json @ 2026-07-27T17:10:30)

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

- **Branch**: iterate/pytest-root-composition
- **Last Commit**: d8009de1 chore(triage): sweep 4 outbox append(s) into branch
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
| evt-024abc36 | grade_snapshot | — | 2026-07-27 |
| evt-aea234e3 | work_completed | iterate (iterate: refuse a multi-root pytest session instead of failing 21 unrelated tests) | 2026-07-27 |
| evt-76f1beff | grade_snapshot | — | 2026-07-27 |
| evt-90ce4f39 | work_completed | iterate (iterate: document the delivery watch in the guide) | 2026-07-27 |
| evt-942e3e04 | grade_snapshot | — | 2026-07-27 |

## Recovery

- **Pipeline**: 1 phases completed
- **Total work events**: 376
- **Last iterate**: change — iterate: refuse a multi-root pytest session instead of failing 21 unrelated tests (2026-07-27)
- **Resume**: `/shipwright-iterate` for next change, or `/shipwright-run` for new pipeline

## Recent Decisions

### ADR-328: Change history as a query over the event log, measured against what it replaced
- **Date:** 2026-07-20
- **Section:** Iterate → campaign S7 derived traceability
- **Run-ID:** iterate-2026-07-19-traceability-derived-view
- **Context:** Campaign decision D4 removed the 'Refined by <run_id>' prose from the requirements catalog because that history was said to live already in commits, the changelog and shipwright_events.jsonl. S6 executed the removal and left the catalog pointing at the event l
