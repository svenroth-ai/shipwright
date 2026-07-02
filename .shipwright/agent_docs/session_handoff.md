---
canon_generated: true
run_id: "iterate-2026-07-02-gh-prompt-ghost-fix"
phase: "iterate"
reason: "iterate: gh-prompt ghost fix (decouple prompt source from cs_alerts + push:main)"
timestamp: "2026-07-02T16:48:24.926158+00:00"
---

# Session Handoff

> Auto-generated 2026-07-02 16:48:24 UTC

## Session Info

- **Session ID**: 25acbbdd-b8f4-43f8-b655-892cb636b579
- **Timestamp**: 2026-07-02 16:48:24 UTC
- **Reason**: iterate: gh-prompt ghost fix (decouple prompt source from cs_alerts + push:main)

## Last Iterate

- **Run ID**: iterate-2026-07-01-diff-coverage-plan
- **Date**: 2026-07-02T11:47:31.023538Z
- **Type**: change
- **Complexity**: trivial
- **Branch**: iterate/diff-coverage-plan
- **ADR**: iterate-2026-07-01-diff-coverage-plan
- **Tests passed**: True
- **Spec**: .shipwright/planning/diff-coverage-roadmap.md

## Current Iterate Progress

- **Branch**: iterate/gh-prompt-ghost-fix
- **Run ID**: iterate-2026-07-02-gh-prompt-ghost-fix
- **Spec**: .shipwright/planning/iterate/2026-07-02-gh-prompt-ghost-fix.md
- **Complexity**: small (classifier estimate; the cautious medium override was dropped after the
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

- **Branch**: iterate/gh-prompt-ghost-fix
- **Last Commit**: 892001e7 docs(planning): phased diff/patch-coverage roadmap (trg-8fdebda3) (#305)
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
| evt-1f234469 | work_completed | iterate (Decouple the prompt-injection triage source from Code Scanning availability (github_triage consumer) + add push:[main] to security.yml so the scan artifact tracks HEAD — fixes the recurring gh-prompt ghost.) | 2026-07-02 |
| evt-0018a555 | work_completed | iterate (Persist the phased diff/patch-coverage roadmap (trg-8fdebda3) as a planning doc) | 2026-07-02 |
| evt-a2c95dc8 | work_completed | iterate (Make the Control Grade composition-neutral: remove the FR-tag-decline penalty + verdict cap so the feature-vs-maintenance work mix no longer affects the grade) | 2026-07-01 |
| evt-f90c7126 | work_completed | iterate (Re-tag mis-filed compliance/security FEATURE work to FR-01.10/FR-01.07 via event_amended overlays; clears the honesty-gate FR-tag decline (Control Grade B->A)) | 2026-06-30 |
| evt-0b72de69 | event_amended | — | 2026-06-30 |

## Recovery

- **Pipeline**: 1 phases completed
- **Total work events**: 240
- **Last iterate**: bug — Decouple the prompt-injection triage source from Code Scanning availability (github_triage consumer) + add push:[main] to security.yml so the scan artifact tracks HEAD — fixes the recurring gh-prompt ghost. (2026-07-02)
- **Resume**: `/shipwright-iterate` for next change, or `/shipwright-run` for new pipeline

## Recent Decisions

### ADR-235: Dedup the bloat-gate Stop block across the plugin fan-out
- **Date:** 2026-06-20
- **Section:** shared/scripts/hooks/bloat_gate_on_stop.py
- **Run-ID:** iterate-2026-06-20-bloat-gate-stop-fanout-dedup
- **Context:** The bloat gate is registered in all 12 plugins, so one Stop event fires it 12x. PR #250 (hook-fanout-dedup) guarded audit/handoff/drift but listed bloat_gate_on_stop as 'already convergent' — wrong: its empty pass path is invisible, masking that the BLOCK path re-emits the full 
