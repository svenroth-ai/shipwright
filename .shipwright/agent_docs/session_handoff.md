---
canon_generated: true
run_id: "iterate-2026-05-02-fix-hook-installer-shape"
phase: "iterate"
reason: "iterate: fix hook_installer Shape A -> B"
timestamp: "2026-05-02T18:55:55.331393+00:00"
---

# Session Handoff

> Auto-generated 2026-05-02 18:55:55 UTC

## Session Info

- **Session ID**: unknown
- **Timestamp**: 2026-05-02 18:55:55 UTC
- **Reason**: iterate: fix hook_installer Shape A -> B

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
- **Last Commit**: 57bc792 chore(release): v0.14.0
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
| — | adopted | — | — |

## Recovery

- **Pipeline**: 0 phases completed
- **Total work events**: 0
- **Resume**: `/shipwright-iterate` for next change, or `/shipwright-run` for new pipeline

## Recent Decisions

### ADR-009: Hook installer writes canonical matcher-group shape
- **Date:** 2026-05-02
- **Section:** Iterate — bug: hook-installer-shape
- **Context:** /shipwright-adopt installed the UserPromptSubmit hook in the legacy bare-command shape (top-level type/command keys); Claude Code's parser requires the canonical matcher-group shape with an inner hooks array. The shipwright monorepo's self-adopt produced a settings.json that Claude Code rejected with 'Expected array, but received undefined', killing al
