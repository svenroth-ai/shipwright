---
canon_generated: true
run_id: "iterate-2026-07-21-fr0115-coverage-bloat"
phase: "iterate"
reason: "iterate: reconcile compliance D1/D3 (FR-01.15 mint coverage) + H2 bloat ratchet"
timestamp: "2026-07-21T22:41:37.612570+00:00"
---

# Session Handoff

> Auto-generated 2026-07-21 22:41:37 UTC

## Session Info

- **Session ID**: 2635282a-8c3e-4568-9bae-d27c6e75bc46
- **Timestamp**: 2026-07-21 22:41:37 UTC
- **Reason**: iterate: reconcile compliance D1/D3 (FR-01.15 mint coverage) + H2 bloat ratchet

## Last Iterate

- **Run ID**: iterate-2026-07-21-fr0115-coverage-bloat
- **Date**: 2026-07-21T22:41:30.231077Z
- **Type**: change
- **Complexity**: medium
- **Branch**: iterate/fr0115-coverage-bloat
- **ADR**: iterate-2026-07-21-fr0115-coverage-bloat
- **Tests passed**: True
- **Spec**: .shipwright/planning/iterate/iterate-2026-07-21-fr0115-coverage-bloat.md

## Current Iterate Progress

- **Branch**: iterate/fr0115-coverage-bloat
- **Run ID**: `iterate-2026-07-21-fr0115-coverage-bloat`
- **Spec**: .shipwright/planning/iterate/iterate-2026-07-21-fr0115-coverage-bloat.md
- **Complexity**: medium (history-calibrated; `prior_source: history`, n=20)
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

- **Branch**: iterate/fr0115-coverage-bloat
- **Last Commit**: 1cfdbbd9 fix(security): close the five open code-scanning alerts, root-fixing where a root fix exists (#424)
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
| evt-622b42cf | grade_snapshot | — | 2026-07-21 |
| evt-6a61ac10 | work_completed | iterate (iterate: reconcile compliance D1/D3 (FR-01.15 mint coverage) + H2 bloat ratchet) | 2026-07-21 |
| evt-ca8ff116 | event_amended | — | 2026-07-21 |
| evt-14387bc7 | grade_snapshot | — | 2026-07-21 |
| evt-36e41db0 | work_completed | iterate (iterate: close the five open GitHub code-scanning alerts) | 2026-07-21 |

## Recovery

- **Pipeline**: 1 phases completed
- **Total work events**: 352
- **Last iterate**: change — iterate: reconcile compliance D1/D3 (FR-01.15 mint coverage) + H2 bloat ratchet (2026-07-21)
- **Resume**: `/shipwright-iterate` for next change, or `/shipwright-run` for new pipeline

## Recent Decisions

### ADR-328: Change history as a query over the event log, measured against what it replaced
- **Date:** 2026-07-20
- **Section:** Iterate → campaign S7 derived traceability
- **Run-ID:** iterate-2026-07-19-traceability-derived-view
- **Context:** Campaign decision D4 removed the 'Refined by <run_id>' prose from the requirements catalog because that history was said to live already in commits, the changelog and shipwright_events.jsonl. S6 executed the removal and left the catalog pointing at the event l
