---
canon_generated: true
run_id: "iterate-2026-07-27-security-coverage-manifest"
phase: "iterate"
reason: "iterate: a security scan records what it did not check"
timestamp: "2026-07-27T11:48:20.486720+00:00"
---

# Session Handoff

> Auto-generated 2026-07-27 11:48:20 UTC

## Session Info

- **Session ID**: 871b1865-c6ae-4724-a105-dc987ddca125
- **Timestamp**: 2026-07-27 11:48:20 UTC
- **Reason**: iterate: a security scan records what it did not check

## Last Iterate

- **Run ID**: iterate-2026-07-27-security-coverage-manifest
- **Date**: 2026-07-27T11:48:13.397870Z
- **Type**: change
- **Complexity**: medium
- **Branch**: iterate/security-coverage-manifest
- **ADR**: iterate-2026-07-27-security-coverage-manifest
- **Tests passed**: True
- **Spec**: .shipwright/planning/iterate/2026-07-27-security-coverage-manifest.md

## Current Iterate Progress

- **Branch**: iterate/security-coverage-manifest
- **Run ID**: iterate-2026-07-27-security-coverage-manifest
- **Spec**: .shipwright/planning/iterate/2026-07-27-security-coverage-manifest.md
- **Complexity**: medium
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

- **Branch**: iterate/security-coverage-manifest
- **Last Commit**: ce149b07 fix(deploy): rollback uses the version it was given, and stops overclaiming the rest (#441)
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
| evt-36951d9d | grade_snapshot | — | 2026-07-27 |
| evt-51c2bffd | work_completed | iterate (security-coverage-manifest) | 2026-07-27 |
| evt-64bc7af0 | grade_snapshot | — | 2026-07-27 |
| evt-19f53577 | grade_snapshot | — | 2026-07-27 |
| evt-78684181 | work_completed | iterate (iterate: the review gate stops being bypassable (fail-closed + fork review)) | 2026-07-27 |

## Recovery

- **Pipeline**: 1 phases completed
- **Total work events**: 367
- **Last iterate**: change — security-coverage-manifest (2026-07-27)
- **Resume**: `/shipwright-iterate` for next change, or `/shipwright-run` for new pipeline

## Recent Decisions

### ADR-328: Change history as a query over the event log, measured against what it replaced
- **Date:** 2026-07-20
- **Section:** Iterate → campaign S7 derived traceability
- **Run-ID:** iterate-2026-07-19-traceability-derived-view
- **Context:** Campaign decision D4 removed the 'Refined by <run_id>' prose from the requirements catalog because that history was said to live already in commits, the changelog and shipwright_events.jsonl. S6 executed the removal and left the catalog pointing at the event l
