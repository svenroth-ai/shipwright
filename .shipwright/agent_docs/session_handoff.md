---
canon_generated: true
run_id: "iterate-2026-07-19-compliance-prework"
phase: "iterate"
reason: "iterate: compliance prework before the requirements-catalog campaign"
timestamp: "2026-07-19T06:10:19.889602+00:00"
---

# Session Handoff

> Auto-generated 2026-07-19 06:10:19 UTC

## Session Info

- **Session ID**: 8e6fa31c-9819-4642-9ae6-d261a2be7a91
- **Timestamp**: 2026-07-19 06:10:19 UTC
- **Reason**: iterate: compliance prework before the requirements-catalog campaign

## Last Iterate

- **Run ID**: iterate-2026-07-19-compliance-prework
- **Date**: 2026-07-19T06:10:14.307772Z
- **Type**: change
- **Complexity**: small
- **Branch**: iterate/compliance-prework
- **ADR**: iterate-2026-07-19-compliance-prework
- **Tests passed**: True
- **Spec**: n/a (small)

## Current Iterate Progress

- **Branch**: iterate/compliance-prework
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

- **Branch**: iterate/compliance-prework
- **Last Commit**: 9cd31961 chore(triage): sweep 4 outbox append(s) into branch
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
| evt-7a612300 | grade_snapshot | — | 2026-07-19 |
| evt-5c18465d | work_completed | iterate (iterate: compliance prework before the requirements-catalog campaign) | 2026-07-19 |
| evt-c3513d1c | grade_snapshot | — | 2026-07-19 |
| evt-16c0251e | work_completed | iterate (iterate: ship the action-pinning posture rule to adopters (trg-0ce59c05)) | 2026-07-19 |
| evt-6a67eebe | grade_snapshot | — | 2026-07-18 |

## Recovery

- **Pipeline**: 1 phases completed
- **Total work events**: 335
- **Last iterate**: change — iterate: compliance prework before the requirements-catalog campaign (2026-07-19)
- **Resume**: `/shipwright-iterate` for next change, or `/shipwright-run` for new pipeline

## Recent Decisions

### ADR-327: Per-test execution-evidence reader as the R1 coverage source
- **Date:** 2026-07-16
- **Section:** Iterate → TT-EV execution-evidence
- **Run-ID:** iterate-2026-07-15-execution-evidence
- **Context:** TT1 shipped the traceability manifest with per-test status/executed, but the only producer of the normalized evidence index was a hand-authored fixture. A static @FR tag proves nothing (Spec 11 R1 / unclosed G5): a skipped/never-run/filtered test would still satisfy a required layer.
- **Decis
