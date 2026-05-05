---
canon_generated: true
run_id: "iterate-2026-05-05-rtm-fr-parser-multicolumn"
phase: "iterate"
reason: "iterate: rtm-fr-parser-multicolumn — FR-table parser accepts 5-col adopt format"
timestamp: "2026-05-05T21:00:22.652710+00:00"
---

# Session Handoff

> Auto-generated 2026-05-05 21:00:22 UTC

## Session Info

- **Session ID**: unknown
- **Timestamp**: 2026-05-05 21:00:22 UTC
- **Reason**: iterate: rtm-fr-parser-multicolumn — FR-table parser accepts 5-col adopt format

## Last Iterate

- **Run ID**: iterate-2026-05-05-plugin-hook-registration
- **Date**: 2026-05-05T16:14:33.428669Z
- **Type**: bug
- **Complexity**: medium
- **Branch**: iterate/plugin-hook-registration
- **ADR**: ADR-030
- **Tests passed**: True
- **Spec**: .shipwright/planning/iterate/2026-05-05-plugin-hook-registration.md

## Current Iterate Progress

- **Branch**: iterate/rtm-fr-parser-multicolumn
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

- **Branch**: iterate/rtm-fr-parser-multicolumn
- **Last Commit**: 389266e chore(release): post-tag canon completion for v0.16.1
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
| evt-678e254b | compliance_update_failed | changelog | 2026-05-05 |
| evt-30f5113f | work_completed | iterate (post-F7 housekeeping + AC-13 P5 fix (active install path) for plugin-hook-registration) | 2026-05-05 |
| evt-7620210f | work_completed | iterate (plugin-owned suggest_iterate hook (ADR-030); retired hook_installer + 7 SKILL.md stanzas + A6 verifier) | 2026-05-05 |
| evt-da156299 | work_completed | iterate (F runner contract mandates reviews (ADR-029)) | 2026-05-04 |
| evt-8ee80d97 | work_completed | iterate (iterate: review-driven hardening (ADR-028 / campaign iterate-skill-hardening Sub-Iterate E)) | 2026-05-04 |

## Recovery

- **Pipeline**: 1 phases completed
- **Total work events**: 13
- **Last iterate**: bug — post-F7 housekeeping + AC-13 P5 fix (active install path) for plugin-hook-registration (2026-05-05)
- **Resume**: `/shipwright-iterate` for next change, or `/shipwright-run` for new pipeline

## Recent Decisions

### ADR-031: FR-table parser accepts 5-col adopt format + drift protection
- **Date:** 2026-05-05
- **Section:** Iterate — bug: rtm-fr-parser-multicolumn
- **Context:** Compliance RTM and drift-audit Group A/D both inlined a regex that only matched the 3-data-column Greenfield FR-table format (`| ID | Text | Priority |`). `/shipwright-adopt` produces 5-data-column tables (`| ID | Name | Priority | Description | Source |`), so every FR row in adopted specs silently failed both parsers — the per-requireme
