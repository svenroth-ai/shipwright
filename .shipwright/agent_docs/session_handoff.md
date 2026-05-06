---
canon_generated: true
run_id: "iterate-2026-05-06-canon-cleanup"
phase: "iterate"
reason: "iterate: refresh dashboard post-F7 (ADR-035)"
timestamp: "2026-05-06T05:27:43.759949+00:00"
---

# Session Handoff

> Auto-generated 2026-05-06 05:27:43 UTC

## Session Info

- **Session ID**: unknown
- **Timestamp**: 2026-05-06 05:27:43 UTC
- **Reason**: iterate: refresh dashboard post-F7 (ADR-035)

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
- **Last Commit**: 50b7127 chore(iterate): F7 event for ADR-035 canon cleanup
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

### ADR-035: Drift-canon cleanup: ALLOWLIST self-adopted records, gitignore proximity, .shipwright/ self-adopt exception
- **Date:** 2026-05-06
- **Section:** Iterate — bug: post-migration canon cleanup
- **Context:** After the .shipwright/<artifact>/ migrations (2026-04-26..29) and self-adoption (2026-05-02), 9 canon tests stayed red on every run. Three classes of false positives: (a) self-adopted records (.shipwright/{adopt,agent_docs,compliance,planning}/...) referencing legacy paths in archived ADRs
