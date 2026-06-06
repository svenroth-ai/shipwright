---
canon_generated: true
run_id: "iterate-2026-06-05-scanner-degraded-marker"
phase: "iterate"
reason: "regenerate derived snapshots after main merge for #157"
timestamp: "2026-06-05T22:07:25.140368+00:00"
---

# Session Handoff

> Auto-generated 2026-06-05 22:07:25 UTC

## Session Info

- **Session ID**: dd680100-0ee5-44a7-bb41-370a09796aa4
- **Timestamp**: 2026-06-05 22:07:25 UTC
- **Reason**: regenerate derived snapshots after main merge for #157

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

- **Branch**: iterate/scanner-degraded-marker
- **Run ID**: iterate-2026-06-05-scanner-degraded-marker
- **Spec**: .shipwright/planning/iterate/2026-06-05-scanner-degraded-marker.md
- **Complexity**: medium + `touches_io_boundary` (subprocess stdout/report-file → `json.loads` → findings; `findings.json` config emission read by the ci gate)
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

- **Branch**: iterate/scanner-degraded-marker
- **Last Commit**: 5b2797d5 Merge origin/main into iterate/scanner-degraded-marker
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
| evt-731a06cd | work_completed | iterate (adopt skill docs: triage.jsonl is tracked, not gitignored (D)) | 2026-06-05 |
| evt-7e3e2dc7 | work_completed | iterate (SBOM cluster dedup-key = signature + manifest_type only (stable id under membership drift)) | 2026-06-05 |
| evt-64ee4ee6 | work_completed | iterate (triage_gc tool: machine-churn-only dismissed-pile compaction) | 2026-06-05 |
| evt-17f29a61 | work_completed | iterate (git-track triage.jsonl: gitignore negation + scaffolder self-heal (C1)) | 2026-06-05 |
| evt-a27ad620 | work_completed | iterate (triage.jsonl merge-safety + leak-guard exemption (like events) — C2) | 2026-06-05 |

## Recovery

- **Pipeline**: 1 phases completed
- **Total work events**: 113
- **Last iterate**: change — adopt skill docs: triage.jsonl is tracked, not gitignored (D) (2026-06-05)
- **Resume**: `/shipwright-iterate` for next change, or `/shipwright-run` for new pipeline

## Recent Decisions

### ADR-120: Dedup SessionStart Phase-Quality injection to once-per-event
- **Date:** 2026-06-02
- **Section:** SessionStart hook (shared/scripts/hooks/capture_session_id.py)
- **Run-ID:** iterate-2026-06-02-sessionstart-dedup-guard
- **Context:** capture_session_id.py is registered as a SessionStart hook in all 12 plugins; Claude Code fires every registered hook with no active-plugin filter, so one SessionStart event ran the Phase-Quality Tier-1 FAIL injection ~12x with the identical block (observed li
