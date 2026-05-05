# Session Handoff

> Auto-generated 2026-05-05 20:08:13 UTC

## Session Info

- **Session ID**: unknown
- **Timestamp**: 2026-05-05 20:08:13 UTC
- **Reason**: release v0.16.1

## Last Iterate

- **Run ID**: iterate-2026-05-05-plugin-hook-registration
- **Date**: 2026-05-05T16:14:33.428669Z
- **Type**: bug
- **Complexity**: medium
- **Branch**: iterate/plugin-hook-registration
- **ADR**: ADR-030
- **Tests passed**: True
- **Spec**: .shipwright/planning/iterate/2026-05-05-plugin-hook-registration.md

## Legacy build state

- **Phase**: design
- **Current Split**: 01-adopted
- **Current Section**: adopted-baseline

- **Splits**: 0/1 complete
- **Sections**: 0/1 complete

## Git State

- **Branch**: main
- **Last Commit**: 337113d chore(release): v0.16.1
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
| evt-30f5113f | work_completed | iterate (post-F7 housekeeping + AC-13 P5 fix (active install path) for plugin-hook-registration) | 2026-05-05 |
| evt-7620210f | work_completed | iterate (plugin-owned suggest_iterate hook (ADR-030); retired hook_installer + 7 SKILL.md stanzas + A6 verifier) | 2026-05-05 |
| evt-da156299 | work_completed | iterate (F runner contract mandates reviews (ADR-029)) | 2026-05-04 |
| evt-8ee80d97 | work_completed | iterate (iterate: review-driven hardening (ADR-028 / campaign iterate-skill-hardening Sub-Iterate E)) | 2026-05-04 |
| evt-c4ae8ef7 | work_completed | iterate (test plugin: boundary coverage report (campaign iterate-skill-hardening Sub-Iterate D, ADR-027)) | 2026-05-03 |

## Recovery

- **Pipeline**: 1 phases completed
- **Total work events**: 13
- **Last iterate**: bug — post-F7 housekeeping + AC-13 P5 fix (active install path) for plugin-hook-registration (2026-05-05)
- **Resume**: `/shipwright-iterate` for next change, or `/shipwright-run` for new pipeline

## Recent Decisions

### ADR-030: suggest_iterate hook is plugin-registered, not project-installed (retire hook_installer)
- **Date:** 2026-05-05
- **Section:** Iterate — bug: plugin-owned UserPromptSubmit hook
- **Context:** After ADR-019/020 fixed the carrier-shape and command-literal of the project-level installer, Claude Code surfaced an explicit error 'Hook command references ${CLAUDE_PLUGIN_ROOT} but the hook is not associated with a plugin' for every UserPromptSubmit on adopted projects. The variable only expands in 
