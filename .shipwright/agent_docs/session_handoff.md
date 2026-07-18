---
canon_generated: true
run_id: "iterate-2026-07-18-fr-authoring-rules"
phase: "iterate"
reason: "iterate: FR-authoring rules — plain business language + capability altitude"
timestamp: "2026-07-18T06:57:33.583714+00:00"
---

# Session Handoff

> Auto-generated 2026-07-18 06:57:33 UTC

## Session Info

- **Session ID**: b81cbdd9-0e92-4b90-a7bc-b582277c381a
- **Timestamp**: 2026-07-18 06:57:33 UTC
- **Reason**: iterate: FR-authoring rules — plain business language + capability altitude

## Last Iterate

- **Run ID**: iterate-2026-07-18-fr-authoring-rules
- **Date**: 2026-07-18T06:41:35.245945Z
- **Type**: change
- **Complexity**: medium
- **Branch**: iterate/fr-authoring-rules
- **ADR**: iterate-2026-07-18-fr-authoring-rules
- **Tests passed**: True
- **Spec**: .shipwright/planning/iterate/iterate-2026-07-18-fr-authoring-rules.md

## Current Iterate Progress

- **Branch**: iterate/fr-authoring-rules
- **Spec**: .shipwright/planning/iterate/iterate-2026-07-18-fr-authoring-rules.md
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

- **Branch**: iterate/fr-authoring-rules
- **Last Commit**: 063dd3d2 feat(fr-authoring): plain-language capability-level FR rules + advisory hygiene audit
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
| evt-8f153abe | grade_snapshot | — | 2026-07-18 |
| evt-5f2814df | grade_snapshot | — | 2026-07-18 |
| evt-07d2258f | work_completed | iterate (iterate: FR-authoring rules — plain business language + capability altitude + advisory hygiene audit) | 2026-07-18 |
| evt-6fabb1e3 | grade_snapshot | — | 2026-07-18 |
| evt-a84a5f44 | work_completed | iterate (Admit test-traceability.json to the churn allowlist + regenerate-staging + integrate rollback (mirror ci-security CR-1), so origin/main merges auto-resolve it instead of aborting) | 2026-07-18 |

## Recovery

- **Pipeline**: 1 phases completed
- **Total work events**: 324
- **Last iterate**: change — iterate: FR-authoring rules — plain business language + capability altitude + advisory hygiene audit (2026-07-18)
- **Resume**: `/shipwright-iterate` for next change, or `/shipwright-run` for new pipeline

## Recent Decisions

### ADR-327: Per-test execution-evidence reader as the R1 coverage source
- **Date:** 2026-07-16
- **Section:** Iterate → TT-EV execution-evidence
- **Run-ID:** iterate-2026-07-15-execution-evidence
- **Context:** TT1 shipped the traceability manifest with per-test status/executed, but the only producer of the normalized evidence index was a hand-authored fixture. A static @FR tag proves nothing (Spec 11 R1 / unclosed G5): a skipped/never-run/filtered test would still satisfy a required layer.
- **Decis
