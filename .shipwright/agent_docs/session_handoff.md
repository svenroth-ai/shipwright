---
canon_generated: true
run_id: "iterate-2026-05-03-changelog-msys-linter"
phase: "iterate"
reason: "iterate: changelog MSYS path-mangling linter"
timestamp: "2026-05-03T18:14:57.614691+00:00"
---

# Session Handoff

> Auto-generated 2026-05-03 18:14:57 UTC

## Session Info

- **Session ID**: unknown
- **Timestamp**: 2026-05-03 18:14:57 UTC
- **Reason**: iterate: changelog MSYS path-mangling linter

## Last Iterate

- **Run ID**: iterate-2026-05-03-hooks-json-quoting
- **Date**: 2026-05-03T15:40:35.711132Z
- **Type**: bug
- **Complexity**: small
- **Branch**: iterate/hooks-json-quoting
- **ADR**: ADR-022
- **Tests passed**: True
- **Spec**: .shipwright/planning/iterate/2026-05-03-hooks-json-quoting.md

## Current Iterate Progress

- **Branch**: iterate/changelog-msys-linter
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

- **Branch**: iterate/changelog-msys-linter
- **Last Commit**: ed4b076 chore(release): post-tag canon completion for v0.15.0
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
| evt-e67c7be3 | phase_completed | changelog | 2026-05-03 |
| evt-ca7b7d64 | work_completed | iterate (hooks.json quoting (deferred from ADR-020)) | 2026-05-03 |
| evt-baaf4b0e | work_completed | iterate (iterate fix: parse_env_file inline-comment stripping + lib copy sync) | 2026-05-03 |
| evt-aab7ddbd | work_completed | iterate (iterate: adopt scaffolds .env.local with profile + framework keys (ADR-021)) | 2026-05-03 |
| evt-b0b9c422 | work_completed | iterate (suggest_iterate hook quoted-path + Shape A/B upgrade-in-place) | 2026-05-03 |

## Recovery

- **Pipeline**: 1 phases completed
- **Total work events**: 7
- **Last iterate**: bug — hooks.json quoting (deferred from ADR-020) (2026-05-03)
- **Resume**: `/shipwright-iterate` for next change, or `/shipwright-run` for new pipeline

## Recent Decisions

### ADR-023: Detect Git-Bash MSYS path-mangling in changelog drop bullets
- **Date:** 2026-05-03
- **Section:** Iterate — bug: changelog MSYS path-mangling linter
- **Context:** During v0.15.0 release prep, an Added bullet appeared as 'C:/Program Files/Git/shipwright-adopt now scaffolds ...' instead of '/shipwright-adopt now scaffolds ...'. Caught at dry-run by hand. Root cause: Git-Bash on Windows auto-converts a leading-slash argv arg into the Bash install root before the receiving Python script sees 
