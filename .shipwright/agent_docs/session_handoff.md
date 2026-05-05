---
canon_generated: true
run_id: "iterate-2026-05-05-adopt-iterate-config"
phase: "iterate"
reason: "iterate: adopt writes shipwright_iterate_config.json (ADR-032)"
timestamp: "2026-05-05T21:39:09.953218+00:00"
---

# Session Handoff

> Auto-generated 2026-05-05 21:39:10 UTC

## Session Info

- **Session ID**: unknown
- **Timestamp**: 2026-05-05 21:39:10 UTC
- **Reason**: iterate: adopt writes shipwright_iterate_config.json (ADR-032)

## Last Iterate

- **Run ID**: iterate-2026-05-05-rtm-fr-parser-multicolumn
- **Date**: 2026-05-05T21:00:28.623150Z
- **Type**: bug
- **Complexity**: small
- **Branch**: iterate/rtm-fr-parser-multicolumn
- **ADR**: ADR-031
- **Tests passed**: True

## Legacy build state

- **Phase**: design
- **Current Split**: 01-adopted
- **Current Section**: adopted-baseline

- **Splits**: 0/1 complete
- **Sections**: 0/1 complete

## Git State

- **Branch**: main
- **Last Commit**: 656f96f fix(compliance): FR-table parser accepts 5-col adopt format (ADR-031)
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
| evt-30338dac | work_completed | iterate (FR-table parser accepts 5-col adopt format + drift protection) | 2026-05-05 |
| evt-678e254b | compliance_update_failed | changelog | 2026-05-05 |
| evt-30f5113f | work_completed | iterate (post-F7 housekeeping + AC-13 P5 fix (active install path) for plugin-hook-registration) | 2026-05-05 |
| evt-7620210f | work_completed | iterate (plugin-owned suggest_iterate hook (ADR-030); retired hook_installer + 7 SKILL.md stanzas + A6 verifier) | 2026-05-05 |
| evt-da156299 | work_completed | iterate (F runner contract mandates reviews (ADR-029)) | 2026-05-04 |

## Recovery

- **Pipeline**: 1 phases completed
- **Total work events**: 14
- **Last iterate**: bug — FR-table parser accepts 5-col adopt format + drift protection (2026-05-05)
- **Resume**: `/shipwright-iterate` for next change, or `/shipwright-run` for new pipeline

## Recent Decisions

### ADR-032: Adopt writes shipwright_iterate_config.json with documented opt-out schema
- **Date:** 2026-05-05
- **Section:** Iterate — bug: adopt writes shipwright_iterate_config.json
- **Context:** shipwright-adopt wrote 6 of 7 documented config files. shipwright_iterate_config.json was missing — the documented opt-out surface for external_review.feedback_iterations and external_code_review.enabled (per iteration-reviews.md:140 and sub-iterate-runner.md:101). Reproduced on the self-adopted shipwright 
