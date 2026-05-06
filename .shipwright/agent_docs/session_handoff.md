---
canon_generated: true
run_id: "iterate-2026-05-06-hooks-consistency-parser"
phase: "iterate"
reason: "iterate: hooks-consistency parser fix (ADR-036)"
timestamp: "2026-05-06T05:33:45.664617+00:00"
---

# Session Handoff

> Auto-generated 2026-05-06 05:33:45 UTC

## Session Info

- **Session ID**: unknown
- **Timestamp**: 2026-05-06 05:33:45 UTC
- **Reason**: iterate: hooks-consistency parser fix (ADR-036)

## Last Iterate

- **Run ID**: iterate-2026-05-06-canon-cleanup
- **Date**: 2026-05-06T05:26:34.856784Z
- **Type**: bug
- **Complexity**: small
- **Branch**: main
- **ADR**: ADR-035
- **Tests passed**: True

## Legacy build state

- **Phase**: design
- **Current Split**: 01-adopted
- **Current Section**: adopted-baseline

- **Splits**: 0/1 complete
- **Sections**: 0/1 complete

## Git State

- **Branch**: main
- **Last Commit**: 0e33f0e chore(iterate): refresh dashboard + handoff post-F7 (ADR-035)
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
| evt-28541d92 | work_completed | iterate (post-migration canon cleanup — 9 tests green) | 2026-05-06 |
| evt-1d597008 | work_completed | iterate (loader deep-merges per-project shipwright_iterate_config.json + cascade helper) | 2026-05-05 |
| evt-82fa35ff | work_completed | iterate (verifier accepts drop-dir entries + dashboard short-SHAs) | 2026-05-05 |
| evt-ee5c8fd8 | work_completed | iterate (adopt writes shipwright_iterate_config.json with documented opt-out schema) | 2026-05-05 |
| evt-30338dac | work_completed | iterate (FR-table parser accepts 5-col adopt format + drift protection) | 2026-05-05 |

## Recovery

- **Pipeline**: 1 phases completed
- **Total work events**: 18
- **Last iterate**: bug — post-migration canon cleanup — 9 tests green (2026-05-06)
- **Resume**: `/shipwright-iterate` for next change, or `/shipwright-run` for new pipeline

## Recent Decisions

### ADR-036: _hook_commands uses shlex.split to handle quoted-path commands
- **Date:** 2026-05-06
- **Section:** Iterate — bug: hooks-consistency parser handles quoted commands
- **Context:** test_phase_plugin_hooks_consistency.py reported 25 failures suggesting plugins were missing capture_session_id/phase_session_start/phase_session_stop hooks. Investigation showed all 8 phase plugins DO register the full chain in their hooks.json — the test's _hook_commands() helper used cmd.split() (whitespace) whi
