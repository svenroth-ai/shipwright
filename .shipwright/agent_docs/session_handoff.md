---
canon_generated: true
run_id: "iterate-2026-07-03-github-triage-outbox-routing"
phase: "iterate"
reason: "iterate: github-triage outbox routing (delivery-gap fix)"
timestamp: "2026-07-03T14:12:16.917807+00:00"
---

# Session Handoff

> Auto-generated 2026-07-03 14:12:16 UTC

## Session Info

- **Session ID**: 25acbbdd-b8f4-43f8-b655-892cb636b579
- **Timestamp**: 2026-07-03 14:12:16 UTC
- **Reason**: iterate: github-triage outbox routing (delivery-gap fix)

## Last Iterate

- **Run ID**: iterate-2026-07-02-gh-prompt-ghost-fix
- **Date**: 2026-07-02T16:48:46.052810Z
- **Type**: bug
- **Complexity**: small
- **Branch**: iterate/gh-prompt-ghost-fix
- **ADR**: iterate-2026-07-02-gh-prompt-ghost-fix
- **Tests passed**: True
- **Spec**: .shipwright/planning/iterate/2026-07-02-gh-prompt-ghost-fix.md

## Current Iterate Progress

- **Branch**: iterate/github-triage-outbox-routing
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

- **Branch**: iterate/github-triage-outbox-routing
- **Last Commit**: 60ef8f7b chore(triage): sweep 1 outbox append(s) into branch
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
| evt-5755f932 | work_completed | iterate (Route github_triage background appends to the gitignored outbox on idle main (should_route_to_outbox) so they reach origin instead of stranding as main-tree drift — closes the delivery gap behind the recurring gh-prompt ghost.) | 2026-07-03 |
| evt-1f234469 | work_completed | iterate (Decouple the prompt-injection triage source from Code Scanning availability (github_triage consumer) + add push:[main] to security.yml so the scan artifact tracks HEAD — fixes the recurring gh-prompt ghost.) | 2026-07-02 |
| evt-0018a555 | work_completed | iterate (Persist the phased diff/patch-coverage roadmap (trg-8fdebda3) as a planning doc) | 2026-07-02 |
| evt-a2c95dc8 | work_completed | iterate (Make the Control Grade composition-neutral: remove the FR-tag-decline penalty + verdict cap so the feature-vs-maintenance work mix no longer affects the grade) | 2026-07-01 |
| evt-f90c7126 | work_completed | iterate (Re-tag mis-filed compliance/security FEATURE work to FR-01.10/FR-01.07 via event_amended overlays; clears the honesty-gate FR-tag decline (Control Grade B->A)) | 2026-06-30 |

## Recovery

- **Pipeline**: 1 phases completed
- **Total work events**: 241
- **Last iterate**: bug — Route github_triage background appends to the gitignored outbox on idle main (should_route_to_outbox) so they reach origin instead of stranding as main-tree drift — closes the delivery gap behind the recurring gh-prompt ghost. (2026-07-03)
- **Resume**: `/shipwright-iterate` for next change, or `/shipwright-run` for new pipeline

## Recent Decisions

### ADR-235: Dedup the bloat-gate Stop block across the plugin fan-out
- **Date:** 2026-06-20
- **Section:** shared/scripts/hooks/bloat_gate_on_stop.py
- **Run-ID:** iterate-2026-06-20-bloat-gate-stop-fanout-dedup
- **Context:** The bloat gate is registered in all 12 plugins, so one Stop event fires it 12x. PR #250 (hook-fanout-dedup) guarded audit/handoff/drift but listed bloat_gate_on_stop as 'already convergent' — wrong: its empty pass path is invisible, masking that the BLOCK path re-emits the full 
