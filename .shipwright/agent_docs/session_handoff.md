---
canon_generated: true
run_id: "iterate-2026-07-15-churn-allowlist-ci-security"
phase: "iterate"
reason: "iterate: admit ci-security.json to the churn-merge allowlist"
timestamp: "2026-07-15T13:09:54.465587+00:00"
---

# Session Handoff

> Auto-generated 2026-07-15 13:09:54 UTC

## Session Info

- **Session ID**: d983bbf3-1318-4c52-b579-b6bdda1d1bd4
- **Timestamp**: 2026-07-15 13:09:54 UTC
- **Reason**: iterate: admit ci-security.json to the churn-merge allowlist

## Last Iterate

- **Run ID**: iterate-2026-07-15-churn-allowlist-ci-security
- **Date**: 2026-07-15T13:09:49.898766Z
- **Type**: bug
- **Complexity**: medium
- **Branch**: iterate/churn-allowlist-ci-security
- **ADR**: iterate-2026-07-15-churn-allowlist-ci-security
- **Tests passed**: True
- **Spec**: .shipwright/planning/iterate/2026-07-15-churn-allowlist-ci-security.md

## Current Iterate Progress

- **Branch**: iterate/churn-allowlist-ci-security
- **Run ID**: iterate-2026-07-15-churn-allowlist-ci-security
- **Spec**: .shipwright/planning/iterate/2026-07-15-churn-allowlist-ci-security.md
- **Complexity**: medium (floor: `cross_component` — the diff touches
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

- **Branch**: iterate/churn-allowlist-ci-security
- **Last Commit**: 7fe025aa chore(triage): sweep 3 outbox append(s) into branch
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
| evt-1f6b2bca | grade_snapshot | — | 2026-07-15 |
| evt-d23adfee | grade_snapshot | — | 2026-07-15 |
| evt-54e93bec | work_completed | iterate (Redirect perf-check integration test --cwd to tmp_path so the runner's triage emission stops leaking into the tracked fixtures dir) | 2026-07-15 |

## Recovery

- **Pipeline**: 1 phases completed
- **Total work events**: 304
- **Last iterate**: bug — admit ci-security.json to the churn-merge allowlist (+ rollback parity) (2026-07-15)
- **Resume**: `/shipwright-iterate` for next change, or `/shipwright-run` for new pipeline

## Recent Decisions

### ADR-326: Per-split phase_completed: dedup on (phase, splitId)
- **Date:** 2026-07-11
- **Section:** iterate/phase-completed-per-split
- **Run-ID:** iterate-2026-07-11-phase-completed-per-split
- **Context:** Multi-split pipeline phases (build/plan) undercounted per-phase duration in the tracked shipwright_events.jsonl: phase_completed deduped by phase alone (first-wins), keeping only the first split's end, while phase_started is already recorded per split.
- **Decision:** Widen the phase_completed d
