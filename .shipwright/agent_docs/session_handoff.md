---
canon_generated: true
run_id: "iterate-2026-07-06-run-board-handoff-banner"
phase: "iterate"
reason: "F11 refresh after ci-security align"
timestamp: "2026-07-06T22:00:58.603930+00:00"
---

# Session Handoff

> Auto-generated 2026-07-06 22:00:58 UTC

## Session Info

- **Session ID**: 49183d12-fa47-474f-aac7-0fa250a8af1d
- **Timestamp**: 2026-07-06 22:00:58 UTC
- **Reason**: F11 refresh after ci-security align

## Last Iterate

- **Run ID**: iterate-2026-07-06-run-board-handoff-banner
- **Date**: 2026-07-06T22:01:15.265115Z
- **Type**: change
- **Complexity**: small
- **Branch**: iterate/run-board-handoff-banner
- **ADR**: iterate-2026-07-06-run-board-handoff-banner
- **Tests passed**: True

## Current Iterate Progress

- **Branch**: iterate/run-board-handoff-banner
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

- **Branch**: iterate/run-board-handoff-banner
- **Last Commit**: 72169ae2 Merge remote-tracking branch 'origin/main' into iterate/run-board-handoff-banner
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
| evt-59cf16c8 | work_completed | iterate (surface-aware /shipwright-run hand-off banner via CLAUDE_CODE_ENTRYPOINT) | 2026-07-06 |
| evt-19078fb5 | work_completed | iterate (Diff-coverage hard flip: drop continue-on-error from the ci.yml 'Diff coverage (gate)' step and remove its ci_gate_allowlist entry so a PR whose changed lines are < 80% covered blocks merge; the CI-gate guard's reverse-drift + stale-entry checks now enforce it stays gating. Ends the warn-only settling window; also dismisses the campaign triage anchors trg-8fdebda3 + trg-76202789.) | 2026-07-06 |
| evt-9153208e | work_completed | iterate (G6: calibrate the cold-repo projector so well-run OSS repos no longer grade F (CI-system-app test-health + PR-head fallback, network PR-association provenance, self-referential-route suppression); empirical gate asserts well-run > deprecated.) | 2026-07-06 |

## Recovery

- **Pipeline**: 1 phases completed
- **Total work events**: 267
- **Last iterate**: change — Compliance dashboard honesty: rewrite the _diff_coverage_block.py wording so diff-coverage reads as a graded Control-Grade Test-Health input (target >=80%), not '(informational, not yet graded)'. Both prior claims became false after Phase 3 (graded) + the Phase-7 hard flip (enforced CI gate). Kept generic (no hardcoded 'blocks merge') since the renderer is repo-agnostic and lights up on any managed repo that produces the transient. (2026-07-06)
- **Resume**: `/shipwright-iterate` for next change, or `/shipwright-run` for new pipeline

## Recent Decisions

### ADR-235: Dedup the bloat-gate Stop block across the plugin fan-out
- **Date:** 2026-06-20
- **Section:** shared/scripts/hooks/bloat_gate_on_stop.py
- **Run-ID:** iterate-2026-06-20-bloat-gate-stop-fanout-dedup
- **Context:** The bloat gate is registered in all 12 plugins, so one Stop event fires it 12x. PR #250 (hook-fanout-dedup) guarded audit/handoff/drift but listed bloat_gate_on_stop as 'already convergent' — wrong: its empty pass path is invisible, masking that the BLOCK path re-emits the full 
