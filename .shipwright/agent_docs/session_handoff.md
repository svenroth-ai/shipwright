---
canon_generated: true
run_id: "iterate-2026-05-03-hooks-json-quoting"
phase: "iterate"
reason: "iterate: hooks.json  quoting (deferred from ADR-020)"
timestamp: "2026-05-03T15:40:31.464228+00:00"
---

# Session Handoff

> Auto-generated 2026-05-03 15:40:31 UTC

## Session Info

- **Session ID**: unknown
- **Timestamp**: 2026-05-03 15:40:31 UTC
- **Reason**: iterate: hooks.json  quoting (deferred from ADR-020)

## Last Iterate

- **Run ID**: iterate-2026-05-03-suggest-iterate-quoted-path
- **Date**: 2026-05-03T12:25:22.988305Z
- **Type**: bug
- **Complexity**: medium
- **Branch**: iterate/suggest-quoted-path-v2
- **ADR**: ADR-020
- **Tests passed**: True
- **Spec**: .shipwright/planning/iterate/2026-05-03-suggest-iterate-quoted-path.md

## Current Iterate Progress

- **Branch**: iterate/hooks-json-quoting
- **Run ID**: iterate-2026-05-03-hooks-json-quoting
- **Spec**: .shipwright/planning/iterate/2026-05-03-hooks-json-quoting.md
- **Complexity**: small (mechanical sweep + 1 regression test; deferred from adr-020)
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

- **Branch**: iterate/hooks-json-quoting
- **Last Commit**: a462487 Merge iterate/suggest-quoted-path-v2: suggest_iterate hook quoted-path + Shape A/B upgrade-in-place (ADR-020, layers on ADR-019)
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
| evt-b0b9c422 | work_completed | iterate (suggest_iterate hook quoted-path + Shape A/B upgrade-in-place) | 2026-05-03 |
| evt-6c637864 | work_completed | iterate (fix hook_installer Shape A -> B) | 2026-05-03 |
| evt-273bbb54 | work_completed | iterate (shipwright-adopt durable fixes (Sub-2A drift detection, 2B test-fixture filter, 2C compliance_bridge sys.path)) | 2026-05-02 |
| evt-e3d2949e | work_completed | iterate (post-adoption framework cleanup (Sub-1A through 1D)) | 2026-05-02 |
| — | adopted | — | — |

## Recovery

- **Pipeline**: 0 phases completed
- **Total work events**: 4
- **Last iterate**: bug — suggest_iterate hook quoted-path + Shape A/B upgrade-in-place (2026-05-03)
- **Resume**: `/shipwright-iterate` for next change, or `/shipwright-run` for new pipeline

## Recent Decisions

### ADR-022: Quote ${CLAUDE_PLUGIN_ROOT} in plugins/*/hooks/hooks.json

> Parallel-iterate note: ADR-021 is reserved for Sven's
> `iterate/adopt-env-local-scaffold` (env.local scaffolding, in flight
> in a parallel session). Renumbered from auto-assigned 021 → 022 here
> to avoid the merge collision since this iterate landed second.

- **Date:** 2026-05-03
- **Section:** Iterate — bug: hooks.json quoting (deferred from ADR-020)
- **Context:** Every plugins/*/hooks/hooks.json embeds uv-run/bash with unqu
