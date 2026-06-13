---
canon_generated: true
run_id: "iterate-2026-06-13-atomic-write-fsync-durability"
phase: "iterate"
reason: "F11 pre-merge refresh: iterate-2026-06-13-atomic-write-fsync-durability"
timestamp: "2026-06-13T11:23:59.355031+00:00"
---

# Session Handoff

> Auto-generated 2026-06-13 11:23:59 UTC

## Session Info

- **Session ID**: 96f26c03-fb2e-4966-891d-b9671b25b403
- **Timestamp**: 2026-06-13 11:23:59 UTC
- **Reason**: F11 pre-merge refresh: iterate-2026-06-13-atomic-write-fsync-durability

## Last Iterate

- **Run ID**: iterate-2026-06-13-atomic-write-fsync-durability
- **Date**: 2026-06-13T11:25:19.204917Z
- **Type**: change
- **Complexity**: medium
- **Branch**: iterate/atomic-write-fsync-durability
- **ADR**: iterate-2026-06-13-atomic-write-fsync-durability
- **Tests passed**: True
- **Spec**: .shipwright/planning/iterate/2026-06-13-atomic-write-fsync-durability.md

## Current Iterate Progress

- **Branch**: iterate/atomic-write-fsync-durability
- **Run ID**: `iterate-2026-06-13-atomic-write-fsync-durability`
- **Spec**: .shipwright/planning/iterate/2026-06-13-atomic-write-fsync-durability.md
- **Complexity**: medium (keyword-sourced, confidence 0.7)
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

- **Branch**: iterate/atomic-write-fsync-durability
- **Last Commit**: a9b3cbe5 Merge remote-tracking branch 'origin/main' into iterate/atomic-write-fsync-durability
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
| evt-35fb72c3 | work_completed | iterate (Read run-config standalone flag without triggering the unlocked legacy migration) | 2026-06-13 |
| evt-c94b50ab | work_completed | iterate (durable atomic writes (fsync) across all atomic writers) | 2026-06-13 |
| evt-0e2c6e4d | work_completed | iterate (sync 6 stale SKILL.md/code/config items to the corrected guide (C1-C6)) | 2026-06-13 |
| evt-b1e3660d | work_completed | iterate (audit-3 WP11a docs/SSoT reconciliation (F3 hooks.json format, F4 registry drift, F9 outbox matrix, F28 F6 decision-drops staging)) | 2026-06-13 |
| evt-208f28f1 | work_completed | iterate (guide.md correctness audit + 21 fixes vs code/ADRs) | 2026-06-13 |

## Recovery

- **Pipeline**: 1 phases completed
- **Total work events**: 178
- **Last iterate**: change — Read run-config standalone flag without triggering the unlocked legacy migration (2026-06-13)
- **Resume**: `/shipwright-iterate` for next change, or `/shipwright-run` for new pipeline

## Recent Decisions

### ADR-196: Coerce explicit-null list/dict fields in WorkEvent.from_dict
- **Date:** 2026-06-12
- **Section:** Iterate — bug: WorkEvent null-frs coercion
- **Run-ID:** iterate-2026-06-12-workevent-null-frs-coerce
- **Context:** A work_completed event carrying an explicit affected_frs:null (vs the normal key-omit) made WorkEvent.from_dict return None: d.get(key, default) only falls back when the key is ABSENT. map_requirements_to_events then iterated None and crashed the whole compliance markdown regen 
