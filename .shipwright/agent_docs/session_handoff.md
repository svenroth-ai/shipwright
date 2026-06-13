---
canon_generated: true
run_id: "iterate-2026-06-13-docs-ssot-reconcile"
phase: "iterate"
reason: "iterate: audit-3 WP11a docs/SSoT reconciliation"
timestamp: "2026-06-13T10:25:13.910813+00:00"
---

# Session Handoff

> Auto-generated 2026-06-13 10:25:13 UTC

## Session Info

- **Session ID**: 118aad1f-bdd5-4952-8f4c-9d0a776d7981
- **Timestamp**: 2026-06-13 10:25:13 UTC
- **Reason**: iterate: audit-3 WP11a docs/SSoT reconciliation

## Last Iterate

- **Run ID**: iterate-2026-06-13-guide-correctness-audit
- **Date**: 2026-06-13T09:21:45.786589Z
- **Type**: change
- **Complexity**: medium
- **Branch**: iterate/guide-correctness-audit
- **ADR**: iterate-2026-06-13-guide-correctness-audit
- **Tests passed**: True
- **Spec**: .shipwright/planning/iterate/2026-06-13-guide-correctness-audit.md

## Current Iterate Progress

- **Branch**: iterate/docs-ssot-reconcile
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

- **Branch**: iterate/docs-ssot-reconcile
- **Last Commit**: c3ee79be docs(guide): correct 21 drifted claims via full code/ADR audit (#230)
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
| evt-b1e3660d | work_completed | iterate (audit-3 WP11a docs/SSoT reconciliation (F3 hooks.json format, F4 registry drift, F9 outbox matrix, F28 F6 decision-drops staging)) | 2026-06-13 |
| evt-208f28f1 | work_completed | iterate (guide.md correctness audit + 21 fixes vs code/ADRs) | 2026-06-13 |
| evt-98471b18 | work_completed | iterate (docs install/Get-Started rewrite + GitHub/auto-merge guide + marketplace metadata parity) | 2026-06-13 |
| evt-a7561bb4 | work_completed | iterate (hook block-channel (WP4): route PostToolUse security-guard reasons to stderr; SessionStart drift gate is honest warn-only via additionalContext) | 2026-06-13 |
| evt-efbff017 | work_completed | iterate (adopt scaffolds profile-aware CodeQL + AUTOMERGE_SETUP doc for brownfield automerge-readiness (bloat-check deferred)) | 2026-06-13 |

## Recovery

- **Pipeline**: 1 phases completed
- **Total work events**: 175
- **Last iterate**: change — audit-3 WP11a docs/SSoT reconciliation (F3 hooks.json format, F4 registry drift, F9 outbox matrix, F28 F6 decision-drops staging) (2026-06-13)
- **Resume**: `/shipwright-iterate` for next change, or `/shipwright-run` for new pipeline

## Recent Decisions

### ADR-196: Coerce explicit-null list/dict fields in WorkEvent.from_dict
- **Date:** 2026-06-12
- **Section:** Iterate — bug: WorkEvent null-frs coercion
- **Run-ID:** iterate-2026-06-12-workevent-null-frs-coerce
- **Context:** A work_completed event carrying an explicit affected_frs:null (vs the normal key-omit) made WorkEvent.from_dict return None: d.get(key, default) only falls back when the key is ABSENT. map_requirements_to_events then iterated None and crashed the whole compliance markdown regen 
