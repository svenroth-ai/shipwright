---
canon_generated: true
run_id: "iterate-2026-07-14-phase-invocation-mode"
phase: "iterate"
reason: "ensure-current pre-merge refresh"
timestamp: "2026-07-14T23:08:05.857788+00:00"
---

# Session Handoff

> Auto-generated 2026-07-14 23:08:05 UTC

## Session Info

- **Session ID**: e5a4eb07-e36d-4d16-9290-2c48215b6b78
- **Timestamp**: 2026-07-14 23:08:05 UTC
- **Reason**: ensure-current pre-merge refresh

## Last Iterate

- **Run ID**: iterate-2026-07-14-phase-invocation-mode
- **Date**: 2026-07-14T23:08:22.204756Z
- **Type**: bug
- **Complexity**: medium
- **Branch**: iterate/phase-invocation-mode
- **ADR**: iterate-2026-07-14-phase-invocation-mode
- **Tests passed**: True
- **Spec**: .shipwright/planning/iterate/2026-07-14-phase-invocation-mode.md

## Current Iterate Progress

- **Branch**: iterate/phase-invocation-mode
- **Spec**: .shipwright/planning/iterate/2026-07-14-phase-invocation-mode.md
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

- **Branch**: iterate/phase-invocation-mode
- **Last Commit**: f2b629cc Merge remote-tracking branch 'origin/main' into iterate/phase-invocation-mode
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
| evt-08956f26 | grade_snapshot | — | 2026-07-14 |
| evt-27b3b806 | grade_snapshot | — | 2026-07-14 |
| evt-97b242ee | grade_snapshot | — | 2026-07-14 |
| evt-ee294bfa | grade_snapshot | — | 2026-07-14 |
| evt-5dc16a45 | work_completed | iterate (F0 parallel suite runner) | 2026-07-14 |

## Recovery

- **Pipeline**: 1 phases completed
- **Total work events**: 301
- **Last iterate**: change — F0 parallel suite runner (2026-07-14)
- **Resume**: `/shipwright-iterate` for next change, or `/shipwright-run` for new pipeline

## Recent Decisions

### ADR-326: Per-split phase_completed: dedup on (phase, splitId)
- **Date:** 2026-07-11
- **Section:** iterate/phase-completed-per-split
- **Run-ID:** iterate-2026-07-11-phase-completed-per-split
- **Context:** Multi-split pipeline phases (build/plan) undercounted per-phase duration in the tracked shipwright_events.jsonl: phase_completed deduped by phase alone (first-wins), keeping only the first split's end, while phase_started is already recorded per split.
- **Decision:** Widen the phase_completed d
