---
canon_generated: true
run_id: "iterate-2026-07-07-diff-coverage-adopt-templates"
phase: "iterate"
reason: "F11 pre-merge refresh"
timestamp: "2026-07-06T22:19:21.443674+00:00"
---

# Session Handoff

> Auto-generated 2026-07-06 22:19:21 UTC

## Session Info

- **Session ID**: 5c5ef9ef-c7b0-4d18-b2ca-e17a75470a7b
- **Timestamp**: 2026-07-06 22:19:21 UTC
- **Reason**: F11 pre-merge refresh

## Last Iterate

- **Run ID**: iterate-2026-07-07-diff-coverage-adopt-templates
- **Date**: 2026-07-06T22:19:25.628329Z
- **Type**: change
- **Complexity**: small
- **Branch**: iterate/diff-coverage-adopt-templates
- **ADR**: iterate-2026-07-07-diff-coverage-adopt-templates
- **Tests passed**: True

## Current Iterate Progress

- **Branch**: iterate/diff-coverage-adopt-templates
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

- **Branch**: iterate/diff-coverage-adopt-templates
- **Last Commit**: 02346b48 Merge remote-tracking branch 'origin/main' into iterate/diff-coverage-adopt-templates
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
| evt-2bcbc1b9 | work_completed | iterate (Diff-coverage adopt-template rollout: add a warn-only diff-coverage job to the two vitest CI templates (ci-supabase-nextjs flat + ci-vite-hono client/server) so every future adopted vitest repo gets a changed-line coverage gate (npm cobertura -> pinned uvx diff-cover@10.3.0 --fail-under=80, continue-on-error, ubuntu-only, PR-gated, dormant). diff-cover resolves each package's paths natively via cobertura <source> (no combine). Proven end-to-end on WebUI PR #205.) | 2026-07-06 |
| evt-b56b6097 | work_completed | iterate (Compliance dashboard honesty: rewrite the _diff_coverage_block.py wording so diff-coverage reads as a graded Control-Grade Test-Health input (target >=80%), not '(informational, not yet graded)'. Both prior claims became false after Phase 3 (graded) + the Phase-7 hard flip (enforced CI gate). Kept generic (no hardcoded 'blocks merge') since the renderer is repo-agnostic and lights up on any managed repo that produces the transient.) | 2026-07-06 |
| evt-0e47577b | work_completed | iterate (Cold-repo Control Grade caps at B (A is authoritative-only): the projector declares change_reconciliation the one expected_dimensions entry so the honesty gate caps a cold headline at B. Heuristic-only; dogfood stays A.) | 2026-07-06 |
| evt-59cf16c8 | work_completed | iterate (surface-aware /shipwright-run hand-off banner via CLAUDE_CODE_ENTRYPOINT) | 2026-07-06 |
| evt-19078fb5 | work_completed | iterate (Diff-coverage hard flip: drop continue-on-error from the ci.yml 'Diff coverage (gate)' step and remove its ci_gate_allowlist entry so a PR whose changed lines are < 80% covered blocks merge; the CI-gate guard's reverse-drift + stale-entry checks now enforce it stays gating. Ends the warn-only settling window; also dismisses the campaign triage anchors trg-8fdebda3 + trg-76202789.) | 2026-07-06 |

## Recovery

- **Pipeline**: 1 phases completed
- **Total work events**: 268
- **Last iterate**: change — Diff-coverage adopt-template rollout: add a warn-only diff-coverage job to the two vitest CI templates (ci-supabase-nextjs flat + ci-vite-hono client/server) so every future adopted vitest repo gets a changed-line coverage gate (npm cobertura -> pinned uvx diff-cover@10.3.0 --fail-under=80, continue-on-error, ubuntu-only, PR-gated, dormant). diff-cover resolves each package's paths natively via cobertura <source> (no combine). Proven end-to-end on WebUI PR #205. (2026-07-06)
- **Resume**: `/shipwright-iterate` for next change, or `/shipwright-run` for new pipeline

## Recent Decisions

### ADR-235: Dedup the bloat-gate Stop block across the plugin fan-out
- **Date:** 2026-06-20
- **Section:** shared/scripts/hooks/bloat_gate_on_stop.py
- **Run-ID:** iterate-2026-06-20-bloat-gate-stop-fanout-dedup
- **Context:** The bloat gate is registered in all 12 plugins, so one Stop event fires it 12x. PR #250 (hook-fanout-dedup) guarded audit/handoff/drift but listed bloat_gate_on_stop as 'already convergent' — wrong: its empty pass path is invisible, masking that the BLOCK path re-emits the full 
