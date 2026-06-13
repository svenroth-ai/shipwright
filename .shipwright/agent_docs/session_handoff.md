---
canon_generated: true
run_id: "iterate-2026-06-13-runconfig-standalone-read"
phase: "iterate"
reason: "iterate: runconfig standalone-flag read locking"
timestamp: "2026-06-13T10:52:08.925087+00:00"
---

# Session Handoff

> Auto-generated 2026-06-13 10:52:08 UTC

## Session Info

- **Session ID**: 2f4ddbdb-5235-4092-9b3c-7c3b85a347f1
- **Timestamp**: 2026-06-13 10:52:08 UTC
- **Reason**: iterate: runconfig standalone-flag read locking

## Last Iterate

- **Run ID**: iterate-2026-06-13-docs-ssot-reconcile
- **Date**: 2026-06-13T10:26:31.177362Z
- **Type**: change
- **Complexity**: small
- **Branch**: iterate/docs-ssot-reconcile
- **ADR**: iterate-2026-06-13-docs-ssot-reconcile
- **Tests passed**: True
- **Spec**: .shipwright/planning/iterate/campaigns/2026-06-10-audit-3-final/sub-iterates/a3-1-docs-ssot-reconcile.md

## Current Iterate Progress

- **Branch**: iterate/runconfig-standalone-read
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

- **Branch**: iterate/runconfig-standalone-read
- **Last Commit**: 8fe2d61e docs(hooks-and-pipeline): reconcile hooks.json format, registry & outbox matrix to shipped reality (audit-3 WP11a) (#232)
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
| evt-0e2c6e4d | work_completed | iterate (sync 6 stale SKILL.md/code/config items to the corrected guide (C1-C6)) | 2026-06-13 |
| evt-b1e3660d | work_completed | iterate (audit-3 WP11a docs/SSoT reconciliation (F3 hooks.json format, F4 registry drift, F9 outbox matrix, F28 F6 decision-drops staging)) | 2026-06-13 |
| evt-208f28f1 | work_completed | iterate (guide.md correctness audit + 21 fixes vs code/ADRs) | 2026-06-13 |
| evt-98471b18 | work_completed | iterate (docs install/Get-Started rewrite + GitHub/auto-merge guide + marketplace metadata parity) | 2026-06-13 |

## Recovery

- **Pipeline**: 1 phases completed
- **Total work events**: 177
- **Last iterate**: change — Read run-config standalone flag without triggering the unlocked legacy migration (2026-06-13)
- **Resume**: `/shipwright-iterate` for next change, or `/shipwright-run` for new pipeline

## Recent Decisions

### ADR-196: Coerce explicit-null list/dict fields in WorkEvent.from_dict
- **Date:** 2026-06-12
- **Section:** Iterate — bug: WorkEvent null-frs coercion
- **Run-ID:** iterate-2026-06-12-workevent-null-frs-coerce
- **Context:** A work_completed event carrying an explicit affected_frs:null (vs the normal key-omit) made WorkEvent.from_dict return None: d.get(key, default) only falls back when the key is ABSENT. map_requirements_to_events then iterated None and crashed the whole compliance markdown regen 
