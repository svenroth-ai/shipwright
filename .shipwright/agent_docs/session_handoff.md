---
canon_generated: true
run_id: "iterate-2026-07-17-arch-doc-refresh-harden"
phase: "iterate"
reason: "merge origin/main reconciliation"
timestamp: "2026-07-17T20:51:30.424518+00:00"
---

# Session Handoff

> Auto-generated 2026-07-17 20:51:30 UTC

## Session Info

- **Session ID**: 1202b22a-3c9e-4c44-b27c-1519865a3d53
- **Timestamp**: 2026-07-17 20:51:30 UTC
- **Reason**: merge origin/main reconciliation

## Last Iterate

- **Run ID**: iterate-2026-07-17-arch-doc-refresh-harden
- **Date**: 2026-07-17T20:52:53.447410Z
- **Type**: change
- **Complexity**: medium
- **Branch**: iterate/arch-doc-refresh-harden
- **ADR**: iterate-2026-07-17-arch-doc-refresh-harden
- **Tests passed**: True
- **Spec**: .shipwright/planning/iterate/2026-07-17-arch-doc-refresh-harden.md

## Current Iterate Progress

- **Branch**: iterate/arch-doc-refresh-harden
- **Run ID**: iterate-2026-07-17-arch-doc-refresh-harden
- **Spec**: .shipwright/planning/iterate/2026-07-17-arch-doc-refresh-harden.md
- **Complexity**: medium (overridden from keyword `large`; force-continue, full rigor)
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

- **Branch**: iterate/arch-doc-refresh-harden
- **Last Commit**: ad00de87 Merge remote-tracking branch 'origin/main' into iterate/arch-doc-refresh-harden
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
| evt-92ef6ad0 | grade_snapshot | — | 2026-07-17 |
| evt-a49e415c | work_completed | iterate (Stage ci-security.json in the churn regenerate follow-up commit (close #375 CR-1 forward-staging gap)) | 2026-07-17 |
| evt-f84c9348 | grade_snapshot | — | 2026-07-17 |
| evt-bd6ec9ec | work_completed | iterate (Canonical run_id changelog-bullet anchor + forward-only shape gate; aggregator stops the ADR-NNN dup; write_decision_log canonicalized; System-Overview mermaid + Data Flow (Plugins/GitHub) refreshed) | 2026-07-17 |
| evt-0cb56caa | grade_snapshot | — | 2026-07-17 |

## Recovery

- **Pipeline**: 1 phases completed
- **Total work events**: 319
- **Last iterate**: bug — Stage ci-security.json in the churn regenerate follow-up commit (close #375 CR-1 forward-staging gap) (2026-07-17)
- **Resume**: `/shipwright-iterate` for next change, or `/shipwright-run` for new pipeline

## Recent Decisions

### ADR-327: Per-test execution-evidence reader as the R1 coverage source
- **Date:** 2026-07-16
- **Section:** Iterate → TT-EV execution-evidence
- **Run-ID:** iterate-2026-07-15-execution-evidence
- **Context:** TT1 shipped the traceability manifest with per-test status/executed, but the only producer of the normalized evidence index was a hand-authored fixture. A static @FR tag proves nothing (Spec 11 R1 / unclosed G5): a skipped/never-run/filtered test would still satisfy a required layer.
- **Decis
