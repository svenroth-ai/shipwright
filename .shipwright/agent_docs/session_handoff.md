---
canon_generated: true
run_id: "iterate-2026-05-03-suggest-iterate-quoted-path"
phase: "iterate"
reason: "iterate: suggest_iterate quoted-path + Shape A→B upgrade-in-place"
timestamp: "2026-05-03T12:25:18.922560+00:00"
---

# Session Handoff

> Auto-generated 2026-05-03 12:25:18 UTC

## Session Info

- **Session ID**: unknown
- **Timestamp**: 2026-05-03 12:25:18 UTC
- **Reason**: iterate: suggest_iterate quoted-path + Shape A→B upgrade-in-place

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

- **Branch**: iterate/suggest-quoted-path-v2
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

- **Branch**: iterate/suggest-quoted-path-v2
- **Last Commit**: 449aacf chore(compliance): refresh artifacts post-rebase + record event for ADR-019
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
| evt-6c637864 | work_completed | iterate (fix hook_installer Shape A -> B) | 2026-05-03 |
| evt-273bbb54 | work_completed | iterate (shipwright-adopt durable fixes (Sub-2A drift detection, 2B test-fixture filter, 2C compliance_bridge sys.path)) | 2026-05-02 |
| evt-e3d2949e | work_completed | iterate (post-adoption framework cleanup (Sub-1A through 1D)) | 2026-05-02 |
| — | adopted | — | — |

## Recovery

- **Pipeline**: 0 phases completed
- **Total work events**: 3
- **Last iterate**: bug — fix hook_installer Shape A -> B (2026-05-03)
- **Resume**: `/shipwright-iterate` for next change, or `/shipwright-run` for new pipeline

## Recent Decisions

### ADR-020: Quote uv-run path placeholders + upgrade legacy hook entries (Shape + command) in place
- **Date:** 2026-05-03
- **Section:** Iterate — bug: suggest_iterate quoted-path + Shape A→B upgrade-in-place
- **Context:** On Windows projects whose path contains spaces (OneDrive-synced "AI Backup - Documents", Windows usernames with spaces, paths under "Program Files"), the suggest_iterate UserPromptSubmit hook installed by /shipwright-adopt and /shipwright-project emitted an unquoted shell command. 
