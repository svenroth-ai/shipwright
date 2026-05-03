---
canon_generated: true
run_id: "iterate-2026-05-02-fix-hook-installer-shape"
phase: "iterate"
reason: "iterate: fix hook_installer Shape A -> B (post-rebase, ADR-019)"
timestamp: "2026-05-03T08:10:28.056605+00:00"
---

# Session Handoff

> Auto-generated 2026-05-03 08:10:28 UTC

## Session Info

- **Session ID**: unknown
- **Timestamp**: 2026-05-03 08:10:28 UTC
- **Reason**: iterate: fix hook_installer Shape A -> B (post-rebase, ADR-019)

## Last Iterate

- **Run ID**: iterate-2026-05-02-adopt-prior-art-and-noise-fixes
- **Date**: 2026-05-02T19:06:52.731942Z
- **Type**: change
- **Complexity**: medium
- **Branch**: iterate/adopt-prior-art-and-noise-fixes
- **ADR**: ADR-018
- **Tests passed**: True
- **Spec**: ~/.claude/plans/du-hast-ein-memory-magical-hippo.md

## Current Iterate Progress

- **Branch**: iterate/fix-hook-installer-shape
- **External Review Marker**: missing

### Mandatory replay on Resume

Before dispatching to the handoff's Remaining phase, run these if missing:
- Finalization (F0–F11) after all mandatory phases pass

## Legacy build state

- **Phase**: build
- **Current Split**: 01-adopted
- **Current Section**: adopted-baseline

- **Splits**: 0/1 complete
- **Sections**: 0/1 complete

## Git State

- **Branch**: iterate/fix-hook-installer-shape
- **Last Commit**: 1ddf9ae fix(adopt): write canonical matcher-group shape for UserPromptSubmit hook
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
| evt-273bbb54 | work_completed | iterate (shipwright-adopt durable fixes (Sub-2A drift detection, 2B test-fixture filter, 2C compliance_bridge sys.path)) | 2026-05-02 |
| evt-e3d2949e | work_completed | iterate (post-adoption framework cleanup (Sub-1A through 1D)) | 2026-05-02 |
| — | adopted | — | — |

## Recovery

- **Pipeline**: 0 phases completed
- **Total work events**: 2
- **Last iterate**: change — shipwright-adopt durable fixes (Sub-2A drift detection, 2B test-fixture filter, 2C compliance_bridge sys.path) (2026-05-02)
- **Resume**: `/shipwright-iterate` for next change, or `/shipwright-run` for new pipeline

## Recent Decisions

### ADR-019: Hook installer writes canonical matcher-group shape
- **Date:** 2026-05-02
- **Section:** Iterate — bug: hook-installer-shape
- **Context:** /shipwright-adopt installed the UserPromptSubmit hook in the legacy bare-command shape (top-level type/command keys); Claude Code's parser requires the canonical matcher-group shape with an inner hooks array. The shipwright monorepo's self-adopt produced a settings.json that Claude Code rejected with 'Expected array, but received undefined', killing al
