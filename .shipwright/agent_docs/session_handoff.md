---
canon_generated: true
run_id: "iterate-2026-06-13-guide-correctness-audit"
phase: "iterate"
reason: "F11 pre-merge refresh: iterate-2026-06-13-guide-correctness-audit"
timestamp: "2026-06-13T09:21:45.201585+00:00"
---

# Session Handoff

> Auto-generated 2026-06-13 09:21:45 UTC

## Session Info

- **Session ID**: 6ae258a2-262e-4e05-9677-bf0575dcdf94
- **Timestamp**: 2026-06-13 09:21:45 UTC
- **Reason**: F11 pre-merge refresh: iterate-2026-06-13-guide-correctness-audit

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

- **Branch**: iterate/guide-correctness-audit
- **Spec**: .shipwright/planning/iterate/2026-06-13-guide-correctness-audit.md
- **Complexity**: medium
- **External Review Marker**: missing

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

- **Branch**: iterate/guide-correctness-audit
- **Last Commit**: b90dfcfc Merge remote-tracking branch 'origin/main' into iterate/guide-correctness-audit
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
| evt-208f28f1 | work_completed | iterate (guide.md correctness audit + 21 fixes vs code/ADRs) | 2026-06-13 |
| evt-98471b18 | work_completed | iterate (docs install/Get-Started rewrite + GitHub/auto-merge guide + marketplace metadata parity) | 2026-06-13 |
| evt-a7561bb4 | work_completed | iterate (hook block-channel (WP4): route PostToolUse security-guard reasons to stderr; SessionStart drift gate is honest warn-only via additionalContext) | 2026-06-13 |
| evt-efbff017 | work_completed | iterate (adopt scaffolds profile-aware CodeQL + AUTOMERGE_SETUP doc for brownfield automerge-readiness (bloat-check deferred)) | 2026-06-13 |
| evt-e7fde4fc | work_completed | iterate (extract diff-driven risk detectors + integration-coverage verifier into dedicated modules to ratchet two bloat baselines down) | 2026-06-13 |

## Recovery

- **Pipeline**: 1 phases completed
- **Total work events**: 174
- **Last iterate**: change — guide.md correctness audit + 21 fixes vs code/ADRs (2026-06-13)
- **Resume**: `/shipwright-iterate` for next change, or `/shipwright-run` for new pipeline

## Recent Decisions

### ADR-196: Coerce explicit-null list/dict fields in WorkEvent.from_dict
- **Date:** 2026-06-12
- **Section:** Iterate — bug: WorkEvent null-frs coercion
- **Run-ID:** iterate-2026-06-12-workevent-null-frs-coerce
- **Context:** A work_completed event carrying an explicit affected_frs:null (vs the normal key-omit) made WorkEvent.from_dict return None: d.get(key, default) only falls back when the key is ABSENT. map_requirements_to_events then iterated None and crashed the whole compliance markdown regen 
