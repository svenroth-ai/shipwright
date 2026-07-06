---
canon_generated: true
run_id: "iterate-2026-07-06-grade-cold-repo-b-cap"
phase: "iterate"
reason: "integrate #332 (diff-coverage dashboard) before B-cap PR"
timestamp: "2026-07-06T20:44:43.547322+00:00"
---

# Session Handoff

> Auto-generated 2026-07-06 20:44:43 UTC

## Session Info

- **Session ID**: fdc9aece-9faa-408e-af7a-7b6e8dbcaa27
- **Timestamp**: 2026-07-06 20:44:43 UTC
- **Reason**: integrate #332 (diff-coverage dashboard) before B-cap PR

## Last Iterate

- **Run ID**: iterate-2026-07-06-grade-cold-repo-b-cap
- **Date**: 2026-07-06T20:45:07.486669Z
- **Type**: change
- **Complexity**: small
- **Branch**: iterate/grade-cold-repo-b-cap
- **ADR**: iterate-2026-07-06-grade-cold-repo-b-cap
- **Tests passed**: True

## Current Iterate Progress

- **Branch**: iterate/grade-cold-repo-b-cap
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

- **Branch**: iterate/grade-cold-repo-b-cap
- **Last Commit**: 39e3bb86 Merge remote-tracking branch 'origin/main' into iterate/grade-cold-repo-b-cap
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
| evt-0e47577b | work_completed | iterate (Cold-repo Control Grade caps at B (A is authoritative-only): the projector declares change_reconciliation the one expected_dimensions entry so the honesty gate caps a cold headline at B. Heuristic-only; dogfood stays A.) | 2026-07-06 |
| evt-19078fb5 | work_completed | iterate (Diff-coverage hard flip: drop continue-on-error from the ci.yml 'Diff coverage (gate)' step and remove its ci_gate_allowlist entry so a PR whose changed lines are < 80% covered blocks merge; the CI-gate guard's reverse-drift + stale-entry checks now enforce it stays gating. Ends the warn-only settling window; also dismisses the campaign triage anchors trg-8fdebda3 + trg-76202789.) | 2026-07-06 |
| evt-9153208e | work_completed | iterate (G6: calibrate the cold-repo projector so well-run OSS repos no longer grade F (CI-system-app test-health + PR-head fallback, network PR-association provenance, self-referential-route suppression); empirical gate asserts well-run > deprecated.) | 2026-07-06 |
| evt-fffb776d | work_completed | iterate (Add a real-PR replay integration suite: pin the actual diff-cover.json from the last 5 monorepo PRs (#324-#328) + a provenance MANIFEST, and replay them through measure_diff_coverage --fail-under 80 as deterministic offline settling-window evidence for the deferred diff-coverage hard-flip.) | 2026-07-06 |

## Recovery

- **Pipeline**: 1 phases completed
- **Total work events**: 266
- **Last iterate**: change — Compliance dashboard honesty: rewrite the _diff_coverage_block.py wording so diff-coverage reads as a graded Control-Grade Test-Health input (target >=80%), not '(informational, not yet graded)'. Both prior claims became false after Phase 3 (graded) + the Phase-7 hard flip (enforced CI gate). Kept generic (no hardcoded 'blocks merge') since the renderer is repo-agnostic and lights up on any managed repo that produces the transient. (2026-07-06)
- **Resume**: `/shipwright-iterate` for next change, or `/shipwright-run` for new pipeline

## Recent Decisions

### ADR-235: Dedup the bloat-gate Stop block across the plugin fan-out
- **Date:** 2026-06-20
- **Section:** shared/scripts/hooks/bloat_gate_on_stop.py
- **Run-ID:** iterate-2026-06-20-bloat-gate-stop-fanout-dedup
- **Context:** The bloat gate is registered in all 12 plugins, so one Stop event fires it 12x. PR #250 (hook-fanout-dedup) guarded audit/handoff/drift but listed bloat_gate_on_stop as 'already convergent' — wrong: its empty pass path is invisible, masking that the BLOCK path re-emits the full 
