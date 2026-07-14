---
canon_generated: true
run_id: "iterate-2026-07-14-f0-parallel-suite"
phase: "iterate"
reason: "iterate: F0 parallel suite runner"
timestamp: "2026-07-14T22:44:30.319245+00:00"
---

# Session Handoff

> Auto-generated 2026-07-14 22:44:30 UTC

## Session Info

- **Session ID**: c40d2729-5d8c-4a25-bcb2-05a6496312c5
- **Timestamp**: 2026-07-14 22:44:30 UTC
- **Reason**: iterate: F0 parallel suite runner

## Last Iterate

- **Run ID**: iterate-2026-07-14-f0-parallel-suite
- **Date**: 2026-07-14T22:43:36.033498Z
- **Type**: change
- **Complexity**: medium
- **Branch**: iterate/f0-parallel-suite
- **ADR**: iterate-2026-07-14-f0-parallel-suite
- **Tests passed**: True
- **Spec**: .shipwright/planning/iterate/2026-07-14-f0-parallel-suite.md

## Current Iterate Progress

- **Branch**: iterate/f0-parallel-suite
- **Run ID**: iterate-2026-07-14-f0-parallel-suite
- **Spec**: .shipwright/planning/iterate/2026-07-14-f0-parallel-suite.md
- **Complexity**: medium
- **External Review Marker**: stale (predates spec (2026-07-14T21:31:17))

### Mandatory replay on Resume

Before dispatching to the handoff's Remaining phase, run these if missing:
- Step 4 — External LLM Review (marker missing/stale)
- Finalization (F0–F11) after all mandatory phases pass

## Legacy build state

- **Phase**: design
- **Current Split**: 01-adopted
- **Current Section**: adopted-baseline

- **Splits**: 0/1 complete
- **Sections**: 0/1 complete

## Git State

- **Branch**: iterate/f0-parallel-suite
- **Last Commit**: e01334a8 chore(triage): sweep 1 outbox append(s) into branch
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
- **Total work events**: 300
- **Last iterate**: change — F0 parallel suite runner (2026-07-14)
- **Resume**: `/shipwright-iterate` for next change, or `/shipwright-run` for new pipeline

## Recent Decisions

### ADR-326: Per-split phase_completed: dedup on (phase, splitId)
- **Date:** 2026-07-11
- **Section:** iterate/phase-completed-per-split
- **Run-ID:** iterate-2026-07-11-phase-completed-per-split
- **Context:** Multi-split pipeline phases (build/plan) undercounted per-phase duration in the tracked shipwright_events.jsonl: phase_completed deduped by phase alone (first-wins), keeping only the first split's end, while phase_started is already recorded per split.
- **Decision:** Widen the phase_completed d
