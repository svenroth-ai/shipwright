---
canon_generated: true
run_id: "iterate-20260505-plugin-hook-registration"
phase: "iterate"
reason: "iterate: plugin-owned UserPromptSubmit hook (ADR-030)"
timestamp: "2026-05-05T16:13:40.671118+00:00"
---

# Session Handoff

> Auto-generated 2026-05-05 16:13:40 UTC

## Session Info

- **Session ID**: unknown
- **Timestamp**: 2026-05-05 16:13:40 UTC
- **Reason**: iterate: plugin-owned UserPromptSubmit hook (ADR-030)

## Last Iterate

- **Run ID**: iterate-2026-05-04-skill-hardening-f-runner-contract-mandates-reviews
- **Date**: 2026-05-04T06:03:30.229325Z
- **Type**: feature
- **Complexity**: small
- **Branch**: iterate/skill-hardening-F-runner-contract-mandates-reviews
- **ADR**: ADR-029
- **Tests passed**: True
- **Spec**: .shipwright/planning/iterate/campaigns/iterate-skill-hardening/sub-iterates/F-runner-contract-mandates-reviews.md

## Current Iterate Progress

- **Branch**: iterate/plugin-hook-registration
- **Run ID**: iterate-20260505-plugin-hook-registration
- **Spec**: .shipwright/planning/iterate/2026-05-05-plugin-hook-registration.md
- **Complexity**: medium (manual override — wide-area refactor across 8
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

- **Branch**: iterate/plugin-hook-registration
- **Last Commit**: 34ce8dc chore(release): post-tag canon completion for v0.16.0
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
| evt-da156299 | work_completed | iterate (F runner contract mandates reviews (ADR-029)) | 2026-05-04 |
| evt-8ee80d97 | work_completed | iterate (iterate: review-driven hardening (ADR-028 / campaign iterate-skill-hardening Sub-Iterate E)) | 2026-05-04 |
| evt-c4ae8ef7 | work_completed | iterate (test plugin: boundary coverage report (campaign iterate-skill-hardening Sub-Iterate D, ADR-027)) | 2026-05-03 |
| evt-530b0980 | work_completed | iterate (changelog MSYS path-mangling linter) | 2026-05-03 |
| evt-e67c7be3 | phase_completed | changelog | 2026-05-03 |

## Recovery

- **Pipeline**: 1 phases completed
- **Total work events**: 11
- **Last iterate**: feature — F runner contract mandates reviews (ADR-029) (2026-05-04)
- **Resume**: `/shipwright-iterate` for next change, or `/shipwright-run` for new pipeline

## Recent Decisions

### ADR-030: suggest_iterate hook is plugin-registered, not project-installed (retire hook_installer)
- **Date:** 2026-05-05
- **Section:** Iterate — bug: plugin-owned UserPromptSubmit hook
- **Context:** After ADR-019/020 fixed the carrier-shape and command-literal of the project-level installer, Claude Code surfaced an explicit error 'Hook command references ${CLAUDE_PLUGIN_ROOT} but the hook is not associated with a plugin' for every UserPromptSubmit on adopted projects. The variable only expands in 
