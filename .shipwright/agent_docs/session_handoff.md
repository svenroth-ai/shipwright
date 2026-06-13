---
canon_generated: true
run_id: "iterate-2026-06-13-docs-install-github-automerge"
phase: "iterate"
reason: "iterate: docs install/Get-Started + GitHub/auto-merge guide + marketplace parity"
timestamp: "2026-06-13T07:22:52.180798+00:00"
---

# Session Handoff

> Auto-generated 2026-06-13 07:22:52 UTC

## Session Info

- **Session ID**: 6ae258a2-262e-4e05-9677-bf0575dcdf94
- **Timestamp**: 2026-06-13 07:22:52 UTC
- **Reason**: iterate: docs install/Get-Started + GitHub/auto-merge guide + marketplace parity

## Last Iterate

- **Run ID**: iterate-2026-06-13-adopt-automerge-readiness
- **Date**: 2026-06-13T06:43:30.814666Z
- **Type**: feature
- **Complexity**: medium
- **Branch**: iterate/adopt-automerge-readiness
- **ADR**: iterate-2026-06-13-adopt-automerge-readiness
- **Description**: adopt scaffolds profile-aware CodeQL + AUTOMERGE_SETUP doc (bloat-check deferred -> trg-33f26f5f)
- **Tests passed**: True
- **Spec**: .shipwright/planning/iterate/2026-06-13-adopt-automerge-readiness.md

## Current Iterate Progress

- **Branch**: iterate/docs-install-github-automerge
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

- **Branch**: iterate/docs-install-github-automerge
- **Last Commit**: feebb255 docs(adopt): note CodeQL + AUTOMERGE_SETUP scaffolding in guide.md Chapter 3.5
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
| evt-98471b18 | work_completed | iterate (docs install/Get-Started rewrite + GitHub/auto-merge guide + marketplace metadata parity) | 2026-06-13 |
| evt-efbff017 | work_completed | iterate (adopt scaffolds profile-aware CodeQL + AUTOMERGE_SETUP doc for brownfield automerge-readiness (bloat-check deferred)) | 2026-06-13 |
| evt-e7fde4fc | work_completed | iterate (extract diff-driven risk detectors + integration-coverage verifier into dedicated modules to ratchet two bloat baselines down) | 2026-06-13 |
| evt-b218f0d8 | work_completed | iterate (run-config concurrency & atomicity (WP2: F11/F12/F13)) | 2026-06-13 |
| evt-8b8ef149 | work_completed | iterate (WP1: phase-session hooks resolve identity from the stdin payload (F1); atomic event-log dedup (F14); phase_failed/stale_stop_rejected event types (F15)) | 2026-06-12 |

## Recovery

- **Pipeline**: 1 phases completed
- **Total work events**: 172
- **Last iterate**: change — docs install/Get-Started rewrite + GitHub/auto-merge guide + marketplace metadata parity (2026-06-13)
- **Resume**: `/shipwright-iterate` for next change, or `/shipwright-run` for new pipeline

## Recent Decisions

### ADR-196: Coerce explicit-null list/dict fields in WorkEvent.from_dict
- **Date:** 2026-06-12
- **Section:** Iterate — bug: WorkEvent null-frs coercion
- **Run-ID:** iterate-2026-06-12-workevent-null-frs-coerce
- **Context:** A work_completed event carrying an explicit affected_frs:null (vs the normal key-omit) made WorkEvent.from_dict return None: d.get(key, default) only falls back when the key is ABSENT. map_requirements_to_events then iterated None and crashed the whole compliance markdown regen 
