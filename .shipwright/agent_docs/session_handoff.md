---
canon_generated: true
run_id: "iterate-2026-07-06-grade-g6-projector-calibration"
phase: "iterate"
reason: "G6 projector calibration complete; empirical gate green, dogfood A"
timestamp: "2026-07-06T17:15:35.088015+00:00"
---

# Session Handoff

> Auto-generated 2026-07-06 17:15:35 UTC

## Session Info

- **Session ID**: fdc9aece-9faa-408e-af7a-7b6e8dbcaa27
- **Timestamp**: 2026-07-06 17:15:35 UTC
- **Reason**: G6 projector calibration complete; empirical gate green, dogfood A

## Last Iterate

- **Run ID**: iterate-2026-07-06-diff-coverage-real-pr-replay
- **Date**: 2026-07-06T14:45:15.363993Z
- **Type**: change
- **Complexity**: small
- **Branch**: iterate/diff-coverage-real-pr-replay
- **ADR**: iterate-2026-07-06-diff-coverage-real-pr-replay
- **Tests passed**: True

## Current Iterate Progress

- **Branch**: iterate/grade-g6-projector-calibration
- **Spec**: .shipwright/planning/iterate/2026-07-06-grade-g6-projector-calibration.md
- **Complexity**: medium (prior_source: history; multi-module projection change + network signal + fixture re-refresh + calibration)
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

- **Branch**: iterate/grade-g6-projector-calibration
- **Last Commit**: fe144fc0 chore(triage): sweep 1 outbox append(s) into branch
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
| evt-9153208e | work_completed | iterate (G6: calibrate the cold-repo projector so well-run OSS repos no longer grade F (CI-system-app test-health + PR-head fallback, network PR-association provenance, self-referential-route suppression); empirical gate asserts well-run > deprecated.) | 2026-07-06 |
| evt-fffb776d | work_completed | iterate (Add a real-PR replay integration suite: pin the actual diff-cover.json from the last 5 monorepo PRs (#324-#328) + a provenance MANIFEST, and replay them through measure_diff_coverage --fail-under 80 as deterministic offline settling-window evidence for the deferred diff-coverage hard-flip.) | 2026-07-06 |
| evt-f75d11f6 | work_completed | iterate (diff-coverage gate hardening: move the warn-only --fail-under decision into a tested measure_diff_coverage.py entrypoint (pure decide_gate), pin diff-cover==10.3.0, migrate to non-deprecated --format flags, and prove the fail-path with a real synthetic-repo integration test; a diff-cover failure now fails closed) | 2026-07-06 |
| evt-ead61d69 | work_completed | iterate (self-heal the shared/ plugin cache on marketplace installs (vendored SessionStart hook, all 12 plugins)) | 2026-07-06 |
| evt-70be807d | work_completed | iterate (G5: shipwright-grade empirical calibration suite (SHA-pinned real-OSS record/replay launch gate) + additive grade_context capture seam. Gate correctly RED (surfaced a projector miscalibration -> G6).) | 2026-07-06 |

## Recovery

- **Pipeline**: 1 phases completed
- **Total work events**: 263
- **Last iterate**: change — G6: calibrate the cold-repo projector so well-run OSS repos no longer grade F (CI-system-app test-health + PR-head fallback, network PR-association provenance, self-referential-route suppression); empirical gate asserts well-run > deprecated. (2026-07-06)
- **Resume**: `/shipwright-iterate` for next change, or `/shipwright-run` for new pipeline

## Recent Decisions

### ADR-235: Dedup the bloat-gate Stop block across the plugin fan-out
- **Date:** 2026-06-20
- **Section:** shared/scripts/hooks/bloat_gate_on_stop.py
- **Run-ID:** iterate-2026-06-20-bloat-gate-stop-fanout-dedup
- **Context:** The bloat gate is registered in all 12 plugins, so one Stop event fires it 12x. PR #250 (hook-fanout-dedup) guarded audit/handoff/drift but listed bloat_gate_on_stop as 'already convergent' — wrong: its empty pass path is invisible, masking that the BLOCK path re-emits the full 
