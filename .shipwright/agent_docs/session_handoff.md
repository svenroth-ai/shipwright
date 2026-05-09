---
canon_generated: true
run_id: "iterate-2026-05-09-known-issues-self-detection-and-cleanup"
phase: "iterate"
reason: "iterate post-F7 dashboard refresh"
timestamp: "2026-05-09T08:03:18.403367+00:00"
---

# Session Handoff

> Auto-generated 2026-05-09 08:03:18 UTC

## Session Info

- **Session ID**: ef6d2ae1-cf77-4229-8751-c0227b1c9dc2
- **Timestamp**: 2026-05-09 08:03:18 UTC
- **Reason**: iterate post-F7 dashboard refresh

## Last Iterate

- **Run ID**: iterate-2026-05-09-known-issues-self-detection-and-cleanup
- **Date**: 2026-05-09T07:59:52.087216Z
- **Type**: bug
- **Complexity**: medium
- **Branch**: iterate/known-issues-self-detection-and-cleanup
- **ADR**: ADR-041
- **Tests passed**: True
- **Spec**: .shipwright/planning/iterate/2026-05-09-known-issues-self-detection-and-cleanup.md

## Current Iterate Progress

- **Branch**: iterate/known-issues-self-detection-and-cleanup
- **Run ID**: iterate-2026-05-09-known-issues-self-detection-and-cleanup
- **Spec**: .shipwright/planning/iterate/2026-05-09-known-issues-self-detection-and-cleanup.md
- **Complexity**: medium (scanner regex change has subtle correctness concerns; bundles two collateral cleanups; external review requested)
- **External Review Marker**: stale (predates spec (2026-05-09T07:45:15))

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

- **Branch**: iterate/known-issues-self-detection-and-cleanup
- **Last Commit**: f8d44da fix(adopt): scanner requires comment-context; remove dead save_session_config
- **Uncommitted Changes**: Yes

## Config Files to Read

- `shipwright_run_config.json` — exists
- `shipwright_project_config.json` — exists
- `shipwright_plan_config.json` — exists
- `shipwright_build_config.json` — exists
- `shipwright_security_config.json` — missing
- `shipwright_compliance_config.json` — exists

## Last Events

| Event | Type | Source | Date |
|-------|------|--------|------|
| evt-c8a57331 | work_completed | iterate (known_issues scanner requires comment context; remove dead save_session_config — 16/16 green) | 2026-05-09 |
| evt-f66286bf | work_completed | iterate (—) | 2026-05-07 |
| evt-623a29ad | work_completed | iterate (—) | 2026-05-07 |
| evt-40c653f7 | work_completed | iterate (F0.5 empirical-test backfill) | 2026-05-06 |
| evt-510b8df3 | work_completed | iterate (F0.5 End-to-End Verification Gate) | 2026-05-06 |

## Recovery

- **Pipeline**: 1 phases completed
- **Total work events**: 24
- **Last iterate**: bug — known_issues scanner requires comment context; remove dead save_session_config — 16/16 green (2026-05-09)
- **Resume**: `/shipwright-iterate` for next change, or `/shipwright-run` for new pipeline

## Recent Decisions

### ADR-041: known-issues scanner requires comment-context; remove dead save_session_config
- **Date:** 2026-05-09
- **Section:** Iterate — bug: known-issues scanner self-detection + cleanup
- **Context:** The TODO/FIXME inventory scanner (.shipwright/agent_docs/known_issues.md) self-matched its own marker tuple and regex pattern, drowning real markers. The on-disk file was also stale and showed 28 markers, mostly fixture noise. shipwright-plan also carried a deprecated save_session_config function with
