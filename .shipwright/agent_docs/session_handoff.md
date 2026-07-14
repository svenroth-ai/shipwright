---
canon_generated: true
run_id: "iterate-2026-07-14-phase-invocation-mode"
phase: "iterate"
reason: "iterate: phase invocation-mode from dispatch token"
timestamp: "2026-07-14T23:08:05.857788+00:00"
---

# Session Handoff

> Auto-generated 2026-07-14 23:08:05 UTC

## Session Info

- **Session ID**: e5a4eb07-e36d-4d16-9290-2c48215b6b78
- **Timestamp**: 2026-07-14 23:08:05 UTC
- **Reason**: iterate: phase invocation-mode from dispatch token

## Last Iterate

- **Run ID**: iterate-2026-07-14-sweep-drift-dismiss-loss
- **Date**: 2026-07-14T20:05:39.541225Z
- **Type**: bug
- **Complexity**: medium
- **Branch**: iterate/sweep-drift-dismiss-loss
- **ADR**: iterate-2026-07-14-sweep-drift-dismiss-loss
- **Description**: The triage outbox sweep silently destroyed operator dismisses: an append stranded in main's tracked triage.jsonl reached no branch, so a status for it looked like an orphan and the #303 quarantine deleted it while reporting success — the item resurrected on the board after every dismiss (webui, trg-6db81c59). The sweep now plans a main-tree drift adoption read-only, decides against the log it would produce, and only then routes the drift into the outbox and restores main's log to HEAD via git; decide() takes the append ids known from main so a legitimate status is never quarantined, unplaceable fails closed, and quarantine/adoption counts reach the operator.
- **Tests passed**: True
- **Spec**: .shipwright/planning/iterate/2026-07-14-sweep-drift-dismiss-loss.md

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
- **Last Commit**: d20415d2 chore(triage): sweep 2 outbox append(s) into branch
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
| evt-55c016da | grade_snapshot | — | 2026-07-14 |
| evt-622c1582 | work_completed | iterate (Phase skills detect invocation mode from the dispatch token, not the never-advanced v1 current_step; update-step made inert in a driven run.) | 2026-07-14 |
| evt-66217d75 | grade_snapshot | — | 2026-07-14 |
| evt-fec83856 | grade_snapshot | — | 2026-07-14 |
| evt-a670d8da | work_completed | iterate (Sweep drift/dismiss-loss fix complete; PR pending) | 2026-07-14 |

## Recovery

- **Pipeline**: 1 phases completed
- **Total work events**: 300
- **Last iterate**: bug — Phase skills detect invocation mode from the dispatch token, not the never-advanced v1 current_step; update-step made inert in a driven run. (2026-07-14)
- **Resume**: `/shipwright-iterate` for next change, or `/shipwright-run` for new pipeline

## Recent Decisions

### ADR-326: Per-split phase_completed: dedup on (phase, splitId)
- **Date:** 2026-07-11
- **Section:** iterate/phase-completed-per-split
- **Run-ID:** iterate-2026-07-11-phase-completed-per-split
- **Context:** Multi-split pipeline phases (build/plan) undercounted per-phase duration in the tracked shipwright_events.jsonl: phase_completed deduped by phase alone (first-wins), keeping only the first split's end, while phase_started is already recorded per split.
- **Decision:** Widen the phase_completed d
