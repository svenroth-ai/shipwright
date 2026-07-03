---
canon_generated: true
run_id: "iterate-2026-07-03-diff-coverage-measure-one-tier"
phase: "iterate"
reason: "iterate: diff-coverage measurement (Phase 1)"
timestamp: "2026-07-03T21:56:46.817090+00:00"
---

# Session Handoff

> Auto-generated 2026-07-03 21:56:46 UTC

## Session Info

- **Session ID**: d6ce5fc1-f421-4efb-8fb5-a04215b1284a
- **Timestamp**: 2026-07-03 21:56:46 UTC
- **Reason**: iterate: diff-coverage measurement (Phase 1)

## Last Iterate

- **Run ID**: iterate-2026-07-03-github-triage-outbox-routing
- **Date**: 2026-07-03T14:12:33.677360Z
- **Type**: bug
- **Complexity**: small
- **Branch**: iterate/github-triage-outbox-routing
- **ADR**: iterate-2026-07-03-github-triage-outbox-routing
- **Tests passed**: True

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
- **Last Commit**: 40d195e3 chore(triage): sweep 2 outbox append(s) into branch
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
| evt-76c97ce2 | work_completed | iterate (diff-coverage Phase 1: shared-tier measurement chain (measure_diff_coverage.py + non-gating CI diff-cover) + gitignored transient + grade-neutral dashboard INFO line) | 2026-07-03 |
| evt-5755f932 | work_completed | iterate (Route github_triage background appends to the gitignored outbox on idle main (should_route_to_outbox) so they reach origin instead of stranding as main-tree drift — closes the delivery gap behind the recurring gh-prompt ghost.) | 2026-07-03 |
| evt-1f234469 | work_completed | iterate (Decouple the prompt-injection triage source from Code Scanning availability (github_triage consumer) + add push:[main] to security.yml so the scan artifact tracks HEAD — fixes the recurring gh-prompt ghost.) | 2026-07-02 |
| evt-0018a555 | work_completed | iterate (Persist the phased diff/patch-coverage roadmap (trg-8fdebda3) as a planning doc) | 2026-07-02 |
| evt-a2c95dc8 | work_completed | iterate (Make the Control Grade composition-neutral: remove the FR-tag-decline penalty + verdict cap so the feature-vs-maintenance work mix no longer affects the grade) | 2026-07-01 |

## Recovery

- **Pipeline**: 1 phases completed
- **Total work events**: 242
- **Last iterate**: feature — diff-coverage Phase 1: shared-tier measurement chain (measure_diff_coverage.py + non-gating CI diff-cover) + gitignored transient + grade-neutral dashboard INFO line (2026-07-03)
- **Resume**: `/shipwright-iterate` for next change, or `/shipwright-run` for new pipeline

## Recent Decisions

### ADR-235: Dedup the bloat-gate Stop block across the plugin fan-out
- **Date:** 2026-06-20
- **Section:** shared/scripts/hooks/bloat_gate_on_stop.py
- **Run-ID:** iterate-2026-06-20-bloat-gate-stop-fanout-dedup
- **Context:** The bloat gate is registered in all 12 plugins, so one Stop event fires it 12x. PR #250 (hook-fanout-dedup) guarded audit/handoff/drift but listed bloat_gate_on_stop as 'already convergent' — wrong: its empty pass path is invisible, masking that the BLOCK path re-emits the full 
