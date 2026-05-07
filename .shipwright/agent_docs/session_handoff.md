---
canon_generated: true
run_id: "iterate-2026-05-07-hooks-json-claude-2-1-132-schema"
phase: "iterate"
reason: "Wrap plugins/*/hooks/hooks.json under top-level hooks key for Claude Code 2.1.132+ schema (ADR-039) + test-side schema unwrap"
timestamp: "2026-05-07T06:35:04.876405+00:00"
---

# Session Handoff

> Auto-generated 2026-05-07 06:35:04 UTC

## Session Info

- **Session ID**: unknown
- **Timestamp**: 2026-05-07 06:35:04 UTC
- **Reason**: Wrap plugins/*/hooks/hooks.json under top-level hooks key for Claude Code 2.1.132+ schema (ADR-039) + test-side schema unwrap

## Last Iterate

- **Run ID**: iterate-2026-05-07-hooks-json-claude-2-1-132-schema
- **Date**: 2026-05-07T00:00:00Z
- **Type**: bug
- **Complexity**: small
- **Branch**: iterate/hooks-json-claude-2-1-132-schema
- **ADR**: ADR-039
- **Tests passed**: True
- **Spec**: .shipwright/planning/iterate/2026-05-07-hooks-json-claude-2-1-132-schema.md

## Current Iterate Progress

- **Branch**: iterate/hooks-json-claude-2-1-132-schema
- **Run ID**: iterate-2026-05-07-hooks-json-claude-2-1-132-schema
- **Spec**: .shipwright/planning/iterate/2026-05-07-hooks-json-claude-2-1-132-schema.md
- **Complexity**: small (mechanical sweep across 12 files + 12 plugin.json version bumps; structural rewrap, no logic change)
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

- **Branch**: iterate/hooks-json-claude-2-1-132-schema
- **Last Commit**: 686e7cc test(hooks): unwrap top-level hooks key in tests that read plugin hooks.json
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
| evt-623a29ad | work_completed | iterate (—) | 2026-05-07 |
| evt-40c653f7 | work_completed | iterate (F0.5 empirical-test backfill) | 2026-05-06 |
| evt-510b8df3 | work_completed | iterate (F0.5 End-to-End Verification Gate) | 2026-05-06 |
| evt-4dcdd82a | work_completed | iterate (hooks-consistency parser handles quoted commands — 27/27 green) | 2026-05-06 |
| evt-28541d92 | work_completed | iterate (post-migration canon cleanup — 9 tests green) | 2026-05-06 |

## Recovery

- **Pipeline**: 1 phases completed
- **Total work events**: 22
- **Last iterate**: change — — (2026-05-07)
- **Resume**: `/shipwright-iterate` for next change, or `/shipwright-run` for new pipeline

## Recent Decisions

### ADR-039: Wrap plugins/*/hooks/hooks.json under top-level `hooks` key for Claude Code 2.1.132+
- **Date:** 2026-05-07
- **Section:** Iterate — bug: hooks.json schema migration to Claude Code 2.1.132+
- **Context:** Claude Code 2.1.132 tightened plugin schema validation. `plugins/*/hooks/hooks.json` is now expected to wrap its event-name dict under a top-level `"hooks"` key. Existing files (post-ADR-019/020, all 12 plugins through v0.17.0) place event names at the document root. Result: plugin load fa
