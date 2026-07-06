---
canon_generated: true
run_id: "iterate-2026-07-06-diff-coverage-dashboard-honesty"
phase: "iterate"
reason: "iterate: diff-coverage dashboard honesty"
timestamp: "2026-07-06T20:38:41.414224+00:00"
---

# Session Handoff

> Auto-generated 2026-07-06 20:38:41 UTC

## Session Info

- **Session ID**: 5c5ef9ef-c7b0-4d18-b2ca-e17a75470a7b
- **Timestamp**: 2026-07-06 20:38:41 UTC
- **Reason**: iterate: diff-coverage dashboard honesty

## Last Iterate

- **Run ID**: iterate-2026-07-06-grade-g6-projector-calibration
- **Date**: 2026-07-06T17:17:30.101328Z
- **Type**: change
- **Complexity**: medium
- **Branch**: iterate/grade-g6-projector-calibration
- **ADR**: iterate-2026-07-06-grade-g6-projector-calibration
- **Tests passed**: True

## Current Iterate Progress

- **Branch**: iterate/diff-coverage-dashboard-honesty
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

- **Branch**: iterate/diff-coverage-dashboard-honesty
- **Last Commit**: 5c20a269 fix(grade): calibrate the cold-repo projector so well-run OSS repos no longer grade F (G6) (#331)
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
| evt-b56b6097 | work_completed | iterate (Compliance dashboard honesty: rewrite the _diff_coverage_block.py wording so diff-coverage reads as a graded Control-Grade Test-Health input (target >=80%), not '(informational, not yet graded)'. Both prior claims became false after Phase 3 (graded) + the Phase-7 hard flip (enforced CI gate). Kept generic (no hardcoded 'blocks merge') since the renderer is repo-agnostic and lights up on any managed repo that produces the transient.) | 2026-07-06 |
| evt-19078fb5 | work_completed | iterate (Diff-coverage hard flip: drop continue-on-error from the ci.yml 'Diff coverage (gate)' step and remove its ci_gate_allowlist entry so a PR whose changed lines are < 80% covered blocks merge; the CI-gate guard's reverse-drift + stale-entry checks now enforce it stays gating. Ends the warn-only settling window; also dismisses the campaign triage anchors trg-8fdebda3 + trg-76202789.) | 2026-07-06 |
| evt-9153208e | work_completed | iterate (G6: calibrate the cold-repo projector so well-run OSS repos no longer grade F (CI-system-app test-health + PR-head fallback, network PR-association provenance, self-referential-route suppression); empirical gate asserts well-run > deprecated.) | 2026-07-06 |
| evt-fffb776d | work_completed | iterate (Add a real-PR replay integration suite: pin the actual diff-cover.json from the last 5 monorepo PRs (#324-#328) + a provenance MANIFEST, and replay them through measure_diff_coverage --fail-under 80 as deterministic offline settling-window evidence for the deferred diff-coverage hard-flip.) | 2026-07-06 |
| evt-f75d11f6 | work_completed | iterate (diff-coverage gate hardening: move the warn-only --fail-under decision into a tested measure_diff_coverage.py entrypoint (pure decide_gate), pin diff-cover==10.3.0, migrate to non-deprecated --format flags, and prove the fail-path with a real synthetic-repo integration test; a diff-cover failure now fails closed) | 2026-07-06 |

## Recovery

- **Pipeline**: 1 phases completed
- **Total work events**: 265
- **Last iterate**: change — Compliance dashboard honesty: rewrite the _diff_coverage_block.py wording so diff-coverage reads as a graded Control-Grade Test-Health input (target >=80%), not '(informational, not yet graded)'. Both prior claims became false after Phase 3 (graded) + the Phase-7 hard flip (enforced CI gate). Kept generic (no hardcoded 'blocks merge') since the renderer is repo-agnostic and lights up on any managed repo that produces the transient. (2026-07-06)
- **Resume**: `/shipwright-iterate` for next change, or `/shipwright-run` for new pipeline

## Recent Decisions

### ADR-235: Dedup the bloat-gate Stop block across the plugin fan-out
- **Date:** 2026-06-20
- **Section:** shared/scripts/hooks/bloat_gate_on_stop.py
- **Run-ID:** iterate-2026-06-20-bloat-gate-stop-fanout-dedup
- **Context:** The bloat gate is registered in all 12 plugins, so one Stop event fires it 12x. PR #250 (hook-fanout-dedup) guarded audit/handoff/drift but listed bloat_gate_on_stop as 'already convergent' — wrong: its empty pass path is invisible, masking that the BLOCK path re-emits the full 
