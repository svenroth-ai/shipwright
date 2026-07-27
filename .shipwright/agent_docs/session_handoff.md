---
canon_generated: true
run_id: "iterate-2026-07-27-security-coverage-manifest"
phase: "iterate"
reason: "iterate: security scan coverage manifest, accepted-findings parity, coverage-gated comparison, severity split at the point of work"
timestamp: "2026-07-27T08:43:59.717363+00:00"
---

# Session Handoff

> Auto-generated 2026-07-27 08:43:59 UTC

## Session Info

- **Session ID**: 871b1865-c6ae-4724-a105-dc987ddca125
- **Timestamp**: 2026-07-27 08:43:59 UTC
- **Reason**: iterate: security scan coverage manifest, accepted-findings parity, coverage-gated comparison, severity split at the point of work

## Last Iterate

- **Run ID**: iterate-2026-07-27-security-coverage-manifest
- **Date**: 2026-07-27T08:43:53.791362Z
- **Type**: change
- **Complexity**: medium
- **Branch**: iterate/security-coverage-manifest
- **ADR**: iterate-2026-07-27-security-coverage-manifest
- **Tests passed**: True
- **Spec**: .shipwright/planning/iterate/2026-07-27-security-coverage-manifest.md

## Current Iterate Progress

- **Branch**: iterate/security-coverage-manifest
- **Run ID**: iterate-2026-07-27-security-coverage-manifest
- **Spec**: .shipwright/planning/iterate/2026-07-27-security-coverage-manifest.md
- **Complexity**: medium
- **External Review Marker**: stale (predates spec (2026-07-27T08:20:04))

### Mandatory replay on Resume

Before dispatching to the handoff's Remaining phase, run these if missing:
- Step 4 — External LLM Review (marker missing/stale)
- Finalization (F0–F11) after all mandatory phases pass

## Legacy build state

- **Phase**: design
- **Current Split**: 01-adopted
- **Current Section**: adopted-baseline

- **Splits**: 0/1 complete
- **Sections**: 0/1 complete

## Git State

- **Branch**: iterate/security-coverage-manifest
- **Last Commit**: 73ead296 chore(triage): sweep 60 outbox append(s) into branch
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
| evt-70b6d56e | grade_snapshot | — | 2026-07-27 |
| evt-a39a5e95 | work_completed | iterate (security-coverage-manifest) | 2026-07-27 |
| evt-2055af94 | grade_snapshot | — | 2026-07-26 |
| evt-ea7203ec | work_completed | iterate (iterate: REQ-3 Phase 2 content round - all 18 requirements walked or minted) | 2026-07-26 |
| evt-6ff6084f | grade_snapshot | — | 2026-07-26 |

## Recovery

- **Pipeline**: 1 phases completed
- **Total work events**: 360
- **Last iterate**: change — security-coverage-manifest (2026-07-27)
- **Resume**: `/shipwright-iterate` for next change, or `/shipwright-run` for new pipeline

## Recent Decisions

### ADR-328: Change history as a query over the event log, measured against what it replaced
- **Date:** 2026-07-20
- **Section:** Iterate → campaign S7 derived traceability
- **Run-ID:** iterate-2026-07-19-traceability-derived-view
- **Context:** Campaign decision D4 removed the 'Refined by <run_id>' prose from the requirements catalog because that history was said to live already in commits, the changelog and shipwright_events.jsonl. S6 executed the removal and left the catalog pointing at the event l
