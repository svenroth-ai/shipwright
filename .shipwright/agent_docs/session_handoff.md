---
canon_generated: true
run_id: "iterate-2026-07-18-fr-fold-map-resolution"
phase: "iterate"
reason: "iterate: resolve tagged FR ids through the spec FR-Fold-Map so granular @covers tags survive a taxonomy fold"
timestamp: "2026-07-18T09:10:19.724932+00:00"
---

# Session Handoff

> Auto-generated 2026-07-18 09:10:19 UTC

## Session Info

- **Session ID**: 3b3d60c1-1bff-42d2-bb57-037c86798a90
- **Timestamp**: 2026-07-18 09:10:19 UTC
- **Reason**: iterate: resolve tagged FR ids through the spec FR-Fold-Map so granular @covers tags survive a taxonomy fold

## Last Iterate

- **Run ID**: iterate-2026-07-18-fr-fold-map-resolution
- **Date**: 2026-07-18T09:10:14.140286Z
- **Type**: change
- **Complexity**: medium
- **Branch**: iterate/fr-fold-map-resolution
- **ADR**: iterate-2026-07-18-fr-fold-map-resolution
- **Tests passed**: True
- **Spec**: .shipwright/planning/iterate/iterate-2026-07-18-fr-fold-map-resolution.md

## Current Iterate Progress

- **Branch**: iterate/fr-fold-map-resolution
- **Run ID**: `iterate-2026-07-18-fr-fold-map-resolution`
- **Spec**: .shipwright/planning/iterate/iterate-2026-07-18-fr-fold-map-resolution.md
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

- **Branch**: iterate/fr-fold-map-resolution
- **Last Commit**: c62e7233 wip: F5/F2/F3a artifacts
- **Uncommitted Changes**: Yes

## Config Files to Read

- `shipwright_run_config.json` — exists
- `shipwright_project_config.json` — exists
- `shipwright_plan_config.json` — exists
- `shipwright_build_config.json` — exists
- `shipwright_security_config.json` — exists
- `shipwright_compliance_config.json` — exists

## Last Events

| Event | Type | Source | Date |
|-------|------|--------|------|
| evt-c5a8b243 | grade_snapshot | — | 2026-07-18 |
| evt-6236a879 | work_completed | iterate (iterate: resolve tagged FR ids through the spec FR-Fold-Map so granular @covers tags survive a taxonomy fold) | 2026-07-18 |
| evt-8f153abe | grade_snapshot | — | 2026-07-18 |
| evt-5f2814df | grade_snapshot | — | 2026-07-18 |
| evt-07d2258f | work_completed | iterate (iterate: FR-authoring rules — plain business language + capability altitude + advisory hygiene audit) | 2026-07-18 |

## Recovery

- **Pipeline**: 1 phases completed
- **Total work events**: 325
- **Last iterate**: change — iterate: resolve tagged FR ids through the spec FR-Fold-Map so granular @covers tags survive a taxonomy fold (2026-07-18)
- **Resume**: `/shipwright-iterate` for next change, or `/shipwright-run` for new pipeline

## Recent Decisions

### ADR-327: Per-test execution-evidence reader as the R1 coverage source
- **Date:** 2026-07-16
- **Section:** Iterate → TT-EV execution-evidence
- **Run-ID:** iterate-2026-07-15-execution-evidence
- **Context:** TT1 shipped the traceability manifest with per-test status/executed, but the only producer of the normalized evidence index was a hand-authored fixture. A static @FR tag proves nothing (Spec 11 R1 / unclosed G5): a skipped/never-run/filtered test would still satisfy a required layer.
- **Decis
