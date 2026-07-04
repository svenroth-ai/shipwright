---
canon_generated: true
run_id: "iterate-2026-07-04-grade-cta-adopt"
phase: "iterate"
reason: "iterate: grade CTA adopt guidance + trusted link"
timestamp: "2026-07-04T13:09:10.541223+00:00"
---

# Session Handoff

> Auto-generated 2026-07-04 13:09:10 UTC

## Session Info

- **Session ID**: 8e84d52f-c16d-4863-a2a4-cdef78f9b4d9
- **Timestamp**: 2026-07-04 13:09:10 UTC
- **Reason**: iterate: grade CTA adopt guidance + trusted link

## Last Iterate

- **Run ID**: iterate-2026-07-04-grade-g3-html-report
- **Date**: 2026-07-04T09:10:12.876538Z
- **Type**: feature
- **Complexity**: medium
- **Branch**: iterate/grade-g3-html-report
- **ADR**: iterate-2026-07-04-grade-g3-html-report
- **Tests passed**: True
- **Spec**: .shipwright/planning/iterate/2026-07-04-grade-g3-html-report.md

## Current Iterate Progress

- **Branch**: iterate/grade-cta-adopt
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

- **Branch**: iterate/grade-cta-adopt
- **Last Commit**: f1b210e2 chore(triage): sweep 4 outbox append(s) into branch
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
| evt-8d01bee7 | work_completed | iterate (grade-cta-adopt) | 2026-07-04 |
| evt-f166acab | work_completed | iterate (Tier-3 pr_review filters producer-generated file-sections (compliance/agent-docs/lockfiles/state-logs) out of the diff before the truncation check, with the excluded list disclosed in PR meta + comment) | 2026-07-04 |
| evt-a5ef23cc | work_completed | iterate (grade-g3-html-report) | 2026-07-04 |
| evt-443a5258 | work_completed | iterate (shipwright-grade G2 external-review follow-up: tier-2 test-check precision (drop build/ci false positives) + code-scanning ref URL-encoding + full-report byte-identical golden + SARIF-JSON clarification) | 2026-07-04 |
| evt-cb7cb6b8 | work_completed | iterate (shipwright-grade G2: light security, dependency, maintainability and network-gated test-health signals for cold repos) | 2026-07-04 |

## Recovery

- **Pipeline**: 1 phases completed
- **Total work events**: 249
- **Last iterate**: change — grade-cta-adopt (2026-07-04)
- **Resume**: `/shipwright-iterate` for next change, or `/shipwright-run` for new pipeline

## Recent Decisions

### ADR-235: Dedup the bloat-gate Stop block across the plugin fan-out
- **Date:** 2026-06-20
- **Section:** shared/scripts/hooks/bloat_gate_on_stop.py
- **Run-ID:** iterate-2026-06-20-bloat-gate-stop-fanout-dedup
- **Context:** The bloat gate is registered in all 12 plugins, so one Stop event fires it 12x. PR #250 (hook-fanout-dedup) guarded audit/handoff/drift but listed bloat_gate_on_stop as 'already convergent' — wrong: its empty pass path is invisible, masking that the BLOCK path re-emits the full 
