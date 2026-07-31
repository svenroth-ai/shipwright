---
canon_generated: true
run_id: "iterate-2026-07-31-review-record-spec-promotion"
phase: "iterate"
reason: "iterate: promote the Stage-1 spec pass into the reviews contract, with a permanent read path for 65 older records"
timestamp: "2026-07-31T23:32:38.909412+00:00"
---

# Session Handoff

> Auto-generated 2026-07-31 23:32:38 UTC

## Session Info

- **Session ID**: unknown
- **Timestamp**: 2026-07-31 23:32:38 UTC
- **Reason**: iterate: promote the Stage-1 spec pass into the reviews contract, with a permanent read path for 65 older records

## Last Iterate

- **Run ID**: iterate-2026-07-31-review-record-spec-promotion
- **Date**: 2026-07-31T23:32:32.469410Z
- **Type**: change
- **Complexity**: medium
- **Branch**: iterate/review-record-spec-promotion
- **ADR**: iterate-2026-07-31-review-record-spec-promotion
- **Tests passed**: True
- **Spec**: .shipwright/planning/iterate/2026-07-31-review-record-spec-promotion.md

## Current Iterate Progress

- **Branch**: iterate/review-record-spec-promotion
- **Run ID**: `iterate-2026-07-31-review-record-spec-promotion`
- **Spec**: .shipwright/planning/iterate/2026-07-31-review-record-spec-promotion.md
- **Complexity**: medium (stage 1 said `small`; the stage-2 repo scout raised it — see below)
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

- **Branch**: iterate/review-record-spec-promotion
- **Last Commit**: 780ebf97 chore(triage): sweep 10 outbox append(s) into branch
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
| evt-4876cc05 | grade_snapshot | — | 2026-07-31 |
| evt-410afe54 | work_completed | iterate (iterate: promote the Stage-1 spec pass into the reviews contract, with a permanent read path for 65 older records) | 2026-07-31 |
| evt-78a81135 | work_completed | iterate (adr-index-churn-register) | 2026-07-31 |
| evt-6d912bb6 | grade_snapshot | — | 2026-07-31 |
| evt-b1b28b77 | grade_snapshot | — | 2026-07-31 |

## Recovery

- **Pipeline**: 1 phases completed
- **Total work events**: 421
- **Last iterate**: change — iterate: promote the Stage-1 spec pass into the reviews contract, with a permanent read path for 65 older records (2026-07-31)
- **Resume**: `/shipwright-iterate` for next change, or `/shipwright-run` for new pipeline

## Recent Decisions

### ADR-328: Change history as a query over the event log, measured against what it replaced
- **Date:** 2026-07-20
- **Section:** Iterate → campaign S7 derived traceability
- **Run-ID:** iterate-2026-07-19-traceability-derived-view
- **Context:** Campaign decision D4 removed the 'Refined by <run_id>' prose from the requirements catalog because that history was said to live already in commits, the changelog and shipwright_events.jsonl. S6 executed the removal and left the catalog pointing at the event l
