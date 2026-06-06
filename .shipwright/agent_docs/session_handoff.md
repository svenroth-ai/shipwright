---
canon_generated: true
run_id: "iterate-2026-06-06-arch-drift-detector"
phase: "iterate"
reason: "F5 content-oracle + canon F11 architecture-doc gate + back-fill"
timestamp: "2026-06-06T07:03:38.252014+00:00"
---

# Session Handoff

> Auto-generated 2026-06-06 07:03:38 UTC

## Session Info

- **Session ID**: d7610364-2946-422f-8141-b3f29bcbbf7e
- **Timestamp**: 2026-06-06 07:03:38 UTC
- **Reason**: F5 content-oracle + canon F11 architecture-doc gate + back-fill

## Last Iterate

- **Run ID**: iterate-2026-06-06-triage-adopt-project-wiring
- **Date**: 2026-06-05T22:07:26.407701Z
- **Type**: change
- **Complexity**: trivial
- **Branch**: iterate/triage-adopt-wiring
- **ADR**: iterate-2026-06-06-triage-adopt-project-wiring
- **Tests passed**: True
- **Spec**: .shipwright/planning/iterate/campaigns/2026-06-05-track-triage-jsonl/sub-iterates/D-adopt-project-wiring.md

## Current Iterate Progress

- **Branch**: iterate/arch-drift-detector
- **Spec**: .shipwright/planning/iterate/2026-06-06-arch-drift-detector.md
- **Complexity**: medium (governance-sensitive: compliance gate behavior + a
- **External Review Marker**: stale (predates spec (2026-06-01T06:00:50))

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

- **Branch**: iterate/arch-drift-detector
- **Last Commit**: 9962ffef Merge #157: fail closed on a degraded scanner leg (scan_errors marker)
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
| evt-277671b1 | work_completed | iterate (F5 architecture-drift detector switched from a git-history oracle (dead on gitignored drops) to content reconciliation (incl. convention); new canon/blocking F11 gate check_architecture_documented sharing one oracle (shared/scripts/lib/architecture_doc.py); dead check_architecture_reviewed + run_cross_artifact_checks removed; 5 orphan architecture.md entries back-filled.) | 2026-06-06 |
| evt-731a06cd | work_completed | iterate (adopt skill docs: triage.jsonl is tracked, not gitignored (D)) | 2026-06-05 |
| evt-7e3e2dc7 | work_completed | iterate (SBOM cluster dedup-key = signature + manifest_type only (stable id under membership drift)) | 2026-06-05 |
| evt-64ee4ee6 | work_completed | iterate (triage_gc tool: machine-churn-only dismissed-pile compaction) | 2026-06-05 |
| evt-17f29a61 | work_completed | iterate (git-track triage.jsonl: gitignore negation + scaffolder self-heal (C1)) | 2026-06-05 |

## Recovery

- **Pipeline**: 1 phases completed
- **Total work events**: 114
- **Last iterate**: change — F5 architecture-drift detector switched from a git-history oracle (dead on gitignored drops) to content reconciliation (incl. convention); new canon/blocking F11 gate check_architecture_documented sharing one oracle (shared/scripts/lib/architecture_doc.py); dead check_architecture_reviewed + run_cross_artifact_checks removed; 5 orphan architecture.md entries back-filled. (2026-06-06)
- **Resume**: `/shipwright-iterate` for next change, or `/shipwright-run` for new pipeline

## Recent Decisions

### ADR-120: Dedup SessionStart Phase-Quality injection to once-per-event
- **Date:** 2026-06-02
- **Section:** SessionStart hook (shared/scripts/hooks/capture_session_id.py)
- **Run-ID:** iterate-2026-06-02-sessionstart-dedup-guard
- **Context:** capture_session_id.py is registered as a SessionStart hook in all 12 plugins; Claude Code fires every registered hook with no active-plugin filter, so one SessionStart event ran the Phase-Quality Tier-1 FAIL injection ~12x with the identical block (observed li
