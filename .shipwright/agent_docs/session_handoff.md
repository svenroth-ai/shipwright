---
canon_generated: true
run_id: "iterate-2026-05-10-stop-hook-schema-fix"
phase: "iterate"
reason: "iterate: Stop hook schema fix"
timestamp: "2026-05-10T18:38:25.495674+00:00"
---

# Session Handoff

> Auto-generated 2026-05-10 18:38:25 UTC

## Session Info

- **Session ID**: 55dd57e4-71d2-49e5-b085-5f39e54a1020
- **Timestamp**: 2026-05-10 18:38:25 UTC
- **Reason**: iterate: Stop hook schema fix

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

- **Branch**: iterate/stop-hook-schema-fix
- **Run ID**: iterate-2026-05-10-stop-hook-schema-fix
- **Spec**: .shipwright/planning/iterate/2026-05-10-stop-hook-schema-fix.md
- **Complexity**: medium
- **External Review Marker**: stale (predates spec (2026-05-09T07:45:15))

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

- **Branch**: iterate/stop-hook-schema-fix
- **Last Commit**: 050982e Merge pull request #23 from svenroth-ai/iterate/known-issues-self-detection-and-cleanup
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

### ADR-042: Stop and SubagentStop hooks emit schema-compliant stdout
- **Date:** 2026-05-10
- **Section:** Iterate — bug: Stop-hook schema compliance
- **Context:** Claude Code surfaced 'Hook JSON output validation failed — (root): Invalid input' for all 35 Stop hooks at every session end. The Stop and SubagentStop schemas only permit 'hookEventName' inside 'hookSpecificOutput'; the existing hook scripts were emitting 'additionalContext' on stdout, which is valid only for SessionStart/PreToolUse/PostTo
