---
canon_generated: true
run_id: "iterate-2026-07-18-requirements-golden-corpus"
phase: "iterate"
reason: "iterate: requirements golden corpus freezing discovery + parser behaviour"
timestamp: "2026-07-18T20:17:24.487328+00:00"
---

# Session Handoff

> Auto-generated 2026-07-18 20:17:24 UTC

## Session Info

- **Session ID**: 8e6fa31c-9819-4642-9ae6-d261a2be7a91
- **Timestamp**: 2026-07-18 20:17:24 UTC
- **Reason**: iterate: requirements golden corpus freezing discovery + parser behaviour

## Last Iterate

- **Run ID**: iterate-2026-07-18-requirements-golden-corpus
- **Date**: 2026-07-18T20:17:17.731937Z
- **Type**: change
- **Complexity**: medium
- **Branch**: iterate/requirements-golden-corpus
- **ADR**: iterate-2026-07-18-requirements-golden-corpus
- **Tests passed**: True
- **Spec**: .shipwright/planning/iterate/iterate-2026-07-18-requirements-golden-corpus.md

## Current Iterate Progress

- **Branch**: iterate/requirements-golden-corpus
- **Run ID**: iterate-2026-07-18-requirements-golden-corpus
- **Spec**: .shipwright/planning/iterate/iterate-2026-07-18-requirements-golden-corpus.md
- **Complexity**: medium (`prior_source: history`, n=20)
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

- **Branch**: iterate/requirements-golden-corpus
- **Last Commit**: 0bcb647e chore(triage): sweep 4 outbox append(s) into branch
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
| evt-06f743dd | grade_snapshot | — | 2026-07-18 |
| evt-43acdff8 | work_completed | iterate (iterate: requirements golden corpus freezing discovery + parser behaviour) | 2026-07-18 |
| evt-a2835609 | grade_snapshot | — | 2026-07-18 |
| evt-695d77cd | grade_snapshot | — | 2026-07-18 |
| evt-14ef5fcb | work_completed | iterate (iterate: enforce record termination + recover record boundaries on the triage log) | 2026-07-18 |

## Recovery

- **Pipeline**: 1 phases completed
- **Total work events**: 330
- **Last iterate**: change — iterate: requirements golden corpus freezing discovery + parser behaviour (2026-07-18)
- **Resume**: `/shipwright-iterate` for next change, or `/shipwright-run` for new pipeline

## Recent Decisions

### ADR-327: Per-test execution-evidence reader as the R1 coverage source
- **Date:** 2026-07-16
- **Section:** Iterate → TT-EV execution-evidence
- **Run-ID:** iterate-2026-07-15-execution-evidence
- **Context:** TT1 shipped the traceability manifest with per-test status/executed, but the only producer of the normalized evidence index was a hand-authored fixture. A static @FR tag proves nothing (Spec 11 R1 / unclosed G5): a skipped/never-run/filtered test would still satisfy a required layer.
- **Decis
