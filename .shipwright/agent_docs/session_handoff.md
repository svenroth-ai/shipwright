---
canon_generated: true
run_id: "iterate-2026-07-06-grade-g5-empirical-suite"
phase: "iterate"
reason: "G5 empirical calibration suite delivered; -m empirical gate RED (projector miscalibration -> G6)"
timestamp: "2026-07-06T11:14:04.882235+00:00"
---

# Session Handoff

> Auto-generated 2026-07-06 11:14:04 UTC

## Session Info

- **Session ID**: a5163991-fcb0-464a-8063-97ae1a1059ee
- **Timestamp**: 2026-07-06 11:14:04 UTC
- **Reason**: G5 empirical calibration suite delivered; -m empirical gate RED (projector miscalibration -> G6)

## Last Iterate

- **Run ID**: iterate-2026-07-06-grade-adopt-path-quotes
- **Date**: 2026-07-06T09:55:28.451735Z
- **Type**: change
- **Complexity**: small
- **Branch**: iterate/grade-adopt-path-quotes
- **ADR**: iterate-2026-07-06-grade-adopt-path-quotes
- **Tests passed**: True

## Current Iterate Progress

- **Branch**: iterate/grade-g5-empirical-suite
- **Spec**: .shipwright/planning/iterate/2026-07-06-grade-g5-empirical-suite.md
- **Complexity**: medium (overrides classifier `small`; new runner + multi-module harness + ci gate + docs + engine-adjacent capture refactor)
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

- **Branch**: iterate/grade-g5-empirical-suite
- **Last Commit**: c1280089 fix(grade,adopt): strip surrounding quotes from path/URL input seams (#325)
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
| evt-70be807d | work_completed | iterate (G5: shipwright-grade empirical calibration suite (SHA-pinned real-OSS record/replay launch gate) + additive grade_context capture seam. Gate correctly RED (surfaced a projector miscalibration -> G6).) | 2026-07-06 |
| evt-24bc2f3a | work_completed | iterate (grade+adopt input path/URL surrounding-quote stripping (WebUI #195 analog)) | 2026-07-06 |
| evt-4d586bd2 | work_completed | iterate (grade-authoritative-disclaimer) | 2026-07-05 |
| evt-17d141eb | work_completed | iterate (diff-coverage CI gate Phase 4 (warn-only): diff-cover --fail-under=80 over the combined coverage.xml, continue-on-error retained (settling window)) | 2026-07-05 |
| evt-4f205233 | work_completed | iterate (grade-report-audience-copy) | 2026-07-04 |

## Recovery

- **Pipeline**: 1 phases completed
- **Total work events**: 259
- **Last iterate**: feature — G5: shipwright-grade empirical calibration suite (SHA-pinned real-OSS record/replay launch gate) + additive grade_context capture seam. Gate correctly RED (surfaced a projector miscalibration -> G6). (2026-07-06)
- **Resume**: `/shipwright-iterate` for next change, or `/shipwright-run` for new pipeline

## Recent Decisions

### ADR-235: Dedup the bloat-gate Stop block across the plugin fan-out
- **Date:** 2026-06-20
- **Section:** shared/scripts/hooks/bloat_gate_on_stop.py
- **Run-ID:** iterate-2026-06-20-bloat-gate-stop-fanout-dedup
- **Context:** The bloat gate is registered in all 12 plugins, so one Stop event fires it 12x. PR #250 (hook-fanout-dedup) guarded audit/handoff/drift but listed bloat_gate_on_stop as 'already convergent' — wrong: its empty pass path is invisible, masking that the BLOCK path re-emits the full 
