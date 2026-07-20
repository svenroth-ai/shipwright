---
canon_generated: true
run_id: "iterate-2026-07-21-fr-history-skip-hardfail"
phase: "iterate"
reason: "iterate: harden two fr-history shallow-clone skip hatches into hard fetch-depth failures (trg-3a131594)"
timestamp: "2026-07-20T22:10:15.358951+00:00"
---

# Session Handoff

> Auto-generated 2026-07-20 22:10:15 UTC

## Session Info

- **Session ID**: 6c3536fe-0c2c-41bb-89a5-ec4014b6c5ee
- **Timestamp**: 2026-07-20 22:10:15 UTC
- **Reason**: iterate: harden two fr-history shallow-clone skip hatches into hard fetch-depth failures (trg-3a131594)

## Last Iterate

- **Run ID**: iterate-2026-07-21-fr-history-skip-hardfail
- **Date**: 2026-07-20T22:10:07.235993Z
- **Type**: change
- **Complexity**: small
- **Branch**: iterate/fr-history-skip-hardfail
- **ADR**: iterate-2026-07-21-fr-history-skip-hardfail
- **Tests passed**: True

## Current Iterate Progress

- **Branch**: iterate/fr-history-skip-hardfail
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

- **Branch**: iterate/fr-history-skip-hardfail
- **Last Commit**: 4062797e fix(finalize): stop flaky idempotency test reddening PRs across a UTC minute boundary (#418)
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
| evt-477d6fa3 | grade_snapshot | — | 2026-07-20 |
| evt-bcb0aa95 | work_completed | iterate (iterate: harden two fr-history shallow-clone skip hatches into hard fetch-depth failures (trg-3a131594)) | 2026-07-20 |
| evt-ec752311 | grade_snapshot | — | 2026-07-20 |
| evt-3f54c795 | work_completed | iterate (adopt FR-id cap: canonical group rollover past 99 detected features) | 2026-07-20 |
| evt-42a87085 | grade_snapshot | — | 2026-07-20 |

## Recovery

- **Pipeline**: 1 phases completed
- **Total work events**: 346
- **Last iterate**: change — iterate: harden two fr-history shallow-clone skip hatches into hard fetch-depth failures (trg-3a131594) (2026-07-20)
- **Resume**: `/shipwright-iterate` for next change, or `/shipwright-run` for new pipeline

## Recent Decisions

### ADR-328: Change history as a query over the event log, measured against what it replaced
- **Date:** 2026-07-20
- **Section:** Iterate → campaign S7 derived traceability
- **Run-ID:** iterate-2026-07-19-traceability-derived-view
- **Context:** Campaign decision D4 removed the 'Refined by <run_id>' prose from the requirements catalog because that history was said to live already in commits, the changelog and shipwright_events.jsonl. S6 executed the removal and left the catalog pointing at the event l
