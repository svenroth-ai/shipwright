---
canon_generated: true
run_id: "iterate-2026-07-23-tests-skipped-tracking"
phase: "iterate"
reason: "iterate: first-class tests.skipped tracking + failure-keyed D4"
timestamp: "2026-07-23T07:19:01.071907+00:00"
---

# Session Handoff

> Auto-generated 2026-07-23 07:19:01 UTC

## Session Info

- **Session ID**: 415d4494-2dda-49f1-9932-c8f88974b90c
- **Timestamp**: 2026-07-23 07:19:01 UTC
- **Reason**: iterate: first-class tests.skipped tracking + failure-keyed D4

## Last Iterate

- **Run ID**: iterate-2026-07-23-tests-skipped-tracking
- **Date**: 2026-07-23T07:18:55.049539Z
- **Type**: change
- **Complexity**: medium
- **Branch**: iterate/tests-skipped-tracking
- **ADR**: iterate-2026-07-23-tests-skipped-tracking
- **Tests passed**: True
- **Spec**: .shipwright/planning/iterate/iterate-2026-07-23-tests-skipped-tracking.md

## Current Iterate Progress

- **Branch**: iterate/tests-skipped-tracking
- **Run ID**: `iterate-2026-07-23-tests-skipped-tracking`
- **Spec**: .shipwright/planning/iterate/iterate-2026-07-23-tests-skipped-tracking.md
- **Complexity**: medium (classifier: `estimate=medium`, `prior_source=keyword`, no risk flags)
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

- **Branch**: iterate/tests-skipped-tracking
- **Last Commit**: 578370ca feat(iterate): record what every review pass found, per run (FR-01.11) (#428)
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
| evt-f8f0c714 | grade_snapshot | — | 2026-07-23 |
| evt-3a175bfa | work_completed | iterate (First-class tests.skipped tracking: --tests-skipped flag + shared tests_block SSOT; D4 keys on genuine failures (charitable when absent) and is re-enabled; test-evidence + dashboard disclose skips; apply_amendments deep-merge opt-in.) | 2026-07-23 |
| evt-e4740235 | grade_snapshot | — | 2026-07-22 |
| evt-83ddad20 | grade_snapshot | — | 2026-07-21 |
| evt-8e3b71af | grade_snapshot | — | 2026-07-21 |

## Recovery

- **Pipeline**: 1 phases completed
- **Total work events**: 356
- **Last iterate**: change — First-class tests.skipped tracking: --tests-skipped flag + shared tests_block SSOT; D4 keys on genuine failures (charitable when absent) and is re-enabled; test-evidence + dashboard disclose skips; apply_amendments deep-merge opt-in. (2026-07-23)
- **Resume**: `/shipwright-iterate` for next change, or `/shipwright-run` for new pipeline

## Recent Decisions

### ADR-328: Change history as a query over the event log, measured against what it replaced
- **Date:** 2026-07-20
- **Section:** Iterate → campaign S7 derived traceability
- **Run-ID:** iterate-2026-07-19-traceability-derived-view
- **Context:** Campaign decision D4 removed the 'Refined by <run_id>' prose from the requirements catalog because that history was said to live already in commits, the changelog and shipwright_events.jsonl. S6 executed the removal and left the catalog pointing at the event l
