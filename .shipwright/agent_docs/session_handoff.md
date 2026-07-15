---
canon_generated: true
run_id: "iterate-2026-07-15-perf-test-triage-leak"
phase: "iterate"
reason: "iterate: perf-test-triage-leak"
timestamp: "2026-07-15T05:48:50.010334+00:00"
---

# Session Handoff

> Auto-generated 2026-07-15 05:48:50 UTC

## Session Info

- **Session ID**: b45e8fa0-3ca5-45d7-8777-83ba8272c639
- **Timestamp**: 2026-07-15 05:48:50 UTC
- **Reason**: iterate: perf-test-triage-leak

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

- **Branch**: iterate/perf-test-triage-leak
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

- **Branch**: iterate/perf-test-triage-leak
- **Last Commit**: 0f0ff9fb chore(triage): sweep 2 outbox append(s) into branch
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
| evt-d23adfee | grade_snapshot | — | 2026-07-15 |
| evt-54e93bec | work_completed | iterate (Redirect perf-check integration test --cwd to tmp_path so the runner's triage emission stops leaking into the tracked fixtures dir) | 2026-07-15 |
| evt-1bd60514 | grade_snapshot | — | 2026-07-15 |
| evt-08956f26 | grade_snapshot | — | 2026-07-14 |
| evt-27b3b806 | grade_snapshot | — | 2026-07-14 |

## Recovery

- **Pipeline**: 1 phases completed
- **Total work events**: 302
- **Last iterate**: bug — Redirect perf-check integration test --cwd to tmp_path so the runner's triage emission stops leaking into the tracked fixtures dir (2026-07-15)
- **Resume**: `/shipwright-iterate` for next change, or `/shipwright-run` for new pipeline

## Recent Decisions

### ADR-326: Per-split phase_completed: dedup on (phase, splitId)
- **Date:** 2026-07-11
- **Section:** iterate/phase-completed-per-split
- **Run-ID:** iterate-2026-07-11-phase-completed-per-split
- **Context:** Multi-split pipeline phases (build/plan) undercounted per-phase duration in the tracked shipwright_events.jsonl: phase_completed deduped by phase alone (first-wins), keeping only the first split's end, while phase_started is already recorded per split.
- **Decision:** Widen the phase_completed d
