---
canon_generated: true
run_id: "iterate-2026-05-03-hooks-json-quoting"
phase: "iterate"
reason: "post-merge regen: bug-3 + hooks-json-quoting"
timestamp: "2026-05-03T15:57:58.168924+00:00"
---

# Session Handoff

> Auto-generated 2026-05-03 15:57:58 UTC

## Session Info

- **Session ID**: unknown
- **Timestamp**: 2026-05-03 15:57:58 UTC
- **Reason**: post-merge regen: bug-3 + hooks-json-quoting

## Last Iterate

- **Run ID**: iterate-2026-05-03-hooks-json-quoting
- **Date**: 2026-05-03T15:40:35.711132Z
- **Type**: bug
- **Complexity**: small
- **Branch**: iterate/hooks-json-quoting
- **ADR**: ADR-022
- **Tests passed**: True
- **Spec**: .shipwright/planning/iterate/2026-05-03-hooks-json-quoting.md

## Legacy build state

- **Phase**: build
- **Current Split**: 01-adopted
- **Current Section**: adopted-baseline

- **Splits**: 0/1 complete
- **Sections**: 0/1 complete

## Git State

- **Branch**: main
- **Last Commit**: 5a34ad7 Merge iterate/hooks-json-quoting: hooks.json ${CLAUDE_PLUGIN_ROOT} quoting (ADR-022, closes ADR-020 follow-up)
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
| evt-ca7b7d64 | work_completed | iterate (hooks.json quoting (deferred from ADR-020)) | 2026-05-03 |
| evt-baaf4b0e | work_completed | iterate (iterate fix: parse_env_file inline-comment stripping + lib copy sync) | 2026-05-03 |
| evt-aab7ddbd | work_completed | iterate (iterate: adopt scaffolds .env.local with profile + framework keys (ADR-021)) | 2026-05-03 |
| evt-b0b9c422 | work_completed | iterate (suggest_iterate hook quoted-path + Shape A/B upgrade-in-place) | 2026-05-03 |
| evt-6c637864 | work_completed | iterate (fix hook_installer Shape A -> B) | 2026-05-03 |

## Recovery

- **Pipeline**: 0 phases completed
- **Total work events**: 7
- **Last iterate**: bug — hooks.json quoting (deferred from ADR-020) (2026-05-03)
- **Resume**: `/shipwright-iterate` for next change, or `/shipwright-run` for new pipeline

## Recent Decisions

### ADR-022: Quote ${CLAUDE_PLUGIN_ROOT} in plugins/*/hooks/hooks.json

> Parallel-iterate note: numbering 022 (not 021) because ADR-021 was
> reserved for Sven's parallel `iterate/adopt-env-local-scaffold`
> (env.local scaffolding) which landed first locally.

- **Date:** 2026-05-03
- **Section:** Iterate — bug: hooks.json quoting (deferred from ADR-020)
- **Context:** Every plugins/*/hooks/hooks.json embeds uv-run/bash with unquoted ${CLAUDE_PLUGIN_ROOT}. Same shell word-splitting bug as ADR-020 (sugg
