---
canon_generated: true
run_id: "iterate-2026-07-03-diff-coverage-measure-one-tier"
phase: "iterate"
reason: "post-merge regen (#311): iterate-2026-07-03-diff-coverage-measure-one-tier"
timestamp: "2026-07-03T22:42:27.621632+00:00"
---

# Session Handoff

> Auto-generated 2026-07-03 22:42:27 UTC

## Session Info

- **Session ID**: d6ce5fc1-f421-4efb-8fb5-a04215b1284a
- **Timestamp**: 2026-07-03 22:42:27 UTC
- **Reason**: post-merge regen (#311): iterate-2026-07-03-diff-coverage-measure-one-tier

## Last Iterate

- **Run ID**: iterate-2026-07-03-grade-g1-projector
- **Date**: 2026-07-03T22:43:13.350885Z
- **Type**: feature
- **Complexity**: medium
- **Branch**: iterate/grade-g1-projector
- **ADR**: iterate-2026-07-03-grade-g1-projector
- **Tests passed**: True
- **Spec**: .shipwright/planning/iterate/2026-07-03-grade-g1-projector.md

## Current Iterate Progress

- **Branch**: iterate/diff-coverage-measure-one-tier
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

- **Branch**: iterate/diff-coverage-measure-one-tier
- **Last Commit**: e1389f03 Merge remote-tracking branch 'origin/main' into iterate/diff-coverage-measure-one-tier
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
| evt-feb2ef5e | work_completed | iterate (shipwright-grade G1: cold-repo signal projector (new read-only plugin)) | 2026-07-03 |
| evt-9d089d93 | work_completed | iterate (Producer-side accepted-risk Semgrep rule tailoring: two opt-in default-off env channels (wholesale exact check_id; owner-scoped mutable-tag via file-read) stop the weekly self-scan re-surfacing 14 dependabot-cooldown + 12 GitHub-owned mutable-tag findings; unpinned third-party actions stay flagged.) | 2026-07-03 |
| evt-76c97ce2 | work_completed | iterate (diff-coverage Phase 1: shared-tier measurement chain (measure_diff_coverage.py + non-gating CI diff-cover) + gitignored transient + grade-neutral dashboard INFO line) | 2026-07-03 |
| evt-5755f932 | work_completed | iterate (Route github_triage background appends to the gitignored outbox on idle main (should_route_to_outbox) so they reach origin instead of stranding as main-tree drift — closes the delivery gap behind the recurring gh-prompt ghost.) | 2026-07-03 |
| evt-1f234469 | work_completed | iterate (Decouple the prompt-injection triage source from Code Scanning availability (github_triage consumer) + add push:[main] to security.yml so the scan artifact tracks HEAD — fixes the recurring gh-prompt ghost.) | 2026-07-02 |

## Recovery

- **Pipeline**: 1 phases completed
- **Total work events**: 244
- **Last iterate**: feature — shipwright-grade G1: cold-repo signal projector (new read-only plugin) (2026-07-03)
- **Resume**: `/shipwright-iterate` for next change, or `/shipwright-run` for new pipeline

## Recent Decisions

### ADR-235: Dedup the bloat-gate Stop block across the plugin fan-out
- **Date:** 2026-06-20
- **Section:** shared/scripts/hooks/bloat_gate_on_stop.py
- **Run-ID:** iterate-2026-06-20-bloat-gate-stop-fanout-dedup
- **Context:** The bloat gate is registered in all 12 plugins, so one Stop event fires it 12x. PR #250 (hook-fanout-dedup) guarded audit/handoff/drift but listed bloat_gate_on_stop as 'already convergent' — wrong: its empty pass path is invisible, masking that the BLOCK path re-emits the full 
