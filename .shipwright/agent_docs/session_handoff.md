---
canon_generated: true
run_id: "iterate-2026-07-15-finalize-utf8-guard"
phase: "iterate"
reason: "ensure-current pre-merge refresh"
timestamp: "2026-07-15T13:22:11.117529+00:00"
---

# Session Handoff

> Auto-generated 2026-07-15 13:22:11 UTC

## Session Info

- **Session ID**: c81674d4-2de4-4fd2-ae13-dd1d3677572c
- **Timestamp**: 2026-07-15 13:22:11 UTC
- **Reason**: ensure-current pre-merge refresh

## Last Iterate

- **Run ID**: iterate-2026-07-15-finalize-utf8-guard
- **Date**: 2026-07-15T13:22:06.591233Z
- **Type**: bug
- **Complexity**: small
- **Branch**: iterate/finalize-utf8-guard
- **ADR**: iterate-2026-07-15-finalize-utf8-guard
- **Tests passed**: True
- **Spec**: n/a (small bug fix; no iterate spec)

## Current Iterate Progress

- **Branch**: iterate/finalize-utf8-guard
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

- **Branch**: iterate/finalize-utf8-guard
- **Last Commit**: dbc32202 Merge remote-tracking branch 'origin/main' into iterate/finalize-utf8-guard
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
| evt-8eef5509 | grade_snapshot | — | 2026-07-15 |
| evt-fdd65a28 | work_completed | iterate (admit ci-security.json to the churn-merge allowlist (+ rollback parity)) | 2026-07-15 |
| evt-7730cf64 | grade_snapshot | — | 2026-07-15 |
| evt-c1b23d3b | work_completed | iterate (Add a UTF-8 reconfigure guard to finalize_iterate.py main() (stdout+stderr) plus two cp1252 subprocess regression tests) | 2026-07-15 |
| evt-1f6b2bca | grade_snapshot | — | 2026-07-15 |

## Recovery

- **Pipeline**: 1 phases completed
- **Total work events**: 305
- **Last iterate**: bug — admit ci-security.json to the churn-merge allowlist (+ rollback parity) (2026-07-15)
- **Resume**: `/shipwright-iterate` for next change, or `/shipwright-run` for new pipeline

## Recent Decisions

### ADR-326: Per-split phase_completed: dedup on (phase, splitId)
- **Date:** 2026-07-11
- **Section:** iterate/phase-completed-per-split
- **Run-ID:** iterate-2026-07-11-phase-completed-per-split
- **Context:** Multi-split pipeline phases (build/plan) undercounted per-phase duration in the tracked shipwright_events.jsonl: phase_completed deduped by phase alone (first-wins), keeping only the first split's end, while phase_started is already recorded per split.
- **Decision:** Widen the phase_completed d
