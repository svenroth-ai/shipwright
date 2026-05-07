---
canon_generated: true
run_id: "iterate-2026-05-07-hooks-json-matcher-string-form"
phase: "iterate"
reason: "Convert PreToolUse/PostToolUse matcher to string form for Claude Code 2.1.132+ schema (ADR-040)"
timestamp: "2026-05-07T08:25:37.334307+00:00"
---

# Session Handoff

> Auto-generated 2026-05-07 08:25:37 UTC

## Session Info

- **Session ID**: unknown
- **Timestamp**: 2026-05-07 08:25:37 UTC
- **Reason**: Convert PreToolUse/PostToolUse matcher to string form for Claude Code 2.1.132+ schema (ADR-040)

## Last Iterate

- **Run ID**: iterate-2026-05-07-hooks-json-matcher-string-form
- **Date**: 2026-05-07T00:00:00Z
- **Type**: bug
- **Complexity**: trivial
- **Branch**: iterate/hooks-json-matcher-string-form
- **ADR**: ADR-040
- **Tests passed**: True
- **Spec**: .shipwright/planning/iterate/2026-05-07-hooks-json-matcher-string-form.md

## Current Iterate Progress

- **Branch**: iterate/hooks-json-matcher-string-form
- **Run ID**: iterate-2026-05-07-hooks-json-matcher-string-form
- **Spec**: .shipwright/planning/iterate/2026-05-07-hooks-json-matcher-string-form.md
- **Complexity**: trivial (3 string edits across 2 files + 1 test extension + 2 version bumps)
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

- **Branch**: iterate/hooks-json-matcher-string-form
- **Last Commit**: 99fc87b fix(plugins): convert PreToolUse/PostToolUse matcher to string form for Claude Code 2.1.132+ schema
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
| evt-f66286bf | work_completed | iterate (—) | 2026-05-07 |
| evt-623a29ad | work_completed | iterate (—) | 2026-05-07 |
| evt-40c653f7 | work_completed | iterate (F0.5 empirical-test backfill) | 2026-05-06 |
| evt-510b8df3 | work_completed | iterate (F0.5 End-to-End Verification Gate) | 2026-05-06 |
| evt-4dcdd82a | work_completed | iterate (hooks-consistency parser handles quoted commands — 27/27 green) | 2026-05-06 |

## Recovery

- **Pipeline**: 1 phases completed
- **Total work events**: 23
- **Last iterate**: change — — (2026-05-07)
- **Resume**: `/shipwright-iterate` for next change, or `/shipwright-run` for new pipeline

## Recent Decisions

### ADR-040: PreToolUse / PostToolUse matcher must be a string under Claude Code 2.1.132+
- **Date:** 2026-05-07
- **Section:** Iterate — bug: hooks.json matcher schema (follow-up to ADR-039)
- **Context:** After ADR-039 wrapped event names under `"hooks"`, `claude plugin list` against the post-merge cache surfaced a SECOND schema tightening: `PreToolUse` / `PostToolUse` matcher fields must now be strings, not the legacy object form `{"tools": ["Bash"]}`. `shipwright-build` reproduces empirically as ✘ f
