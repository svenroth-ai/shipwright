---
canon_generated: true
run_id: "iterate-2026-05-27-guide-readme-refresh"
phase: "iterate"
reason: "iterate finalization"
timestamp: "2026-05-27T20:42:50.226242+00:00"
---

# Session Handoff

> Auto-generated 2026-05-27 20:42:50 UTC

## Session Info

- **Session ID**: 4e2a1fb9-2941-47d7-b901-a5ce1e500c0f
- **Timestamp**: 2026-05-27 20:42:50 UTC
- **Reason**: iterate finalization

## Last Iterate

- **Run ID**: iterate-2026-05-27-sbom-license-resolve
- **Date**: 2026-05-27T15:27:25.850566Z
- **Type**: change
- **Complexity**: trivial
- **Branch**: iterate/sbom-license-resolve
- **ADR**: iterate-2026-05-27-sbom-license-resolve
- **Tests passed**: True

## Current Iterate Progress

- **Branch**: iterate/guide-readme-refresh
- **External Review Marker**: completed (external_review_state.json @ 2026-05-27T07:11:03)

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

- **Branch**: iterate/guide-readme-refresh
- **Last Commit**: 7a77b29 docs(adr): mark ADR-090 split as permanent exception after re-evaluation
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
| evt-13153a5c | work_completed | iterate (Refresh docs/guide.md and README.md with Campaign A/B + ADR-060/061/062/089/090 + F7b + runtime/snapshot split + bloat anti-ratchet hook + plugin-cache drift check) | 2026-05-27 |
| evt-536e20a7 | work_completed | iterate (Refresh SBOM after syncing dev extras across plugin workspaces; clears 4 stale triage entries (pytest/pytest-mock now resolve as MIT)) | 2026-05-27 |
| evt-bf6d663c | work_completed | iterate (Correction event: spec_impact reclassified to none with justification (supersedes evt-5aca940d).) | 2026-05-27 |
| evt-5aca940d | work_completed | iterate (Runtime/snapshot split for agent-doc trio + hard-gated finalize repair pass + audit_staleness coverage extension + merge-not-rebase doc convention.) | 2026-05-27 |
| evt-e3dd6850 | work_completed | iterate (B8: shared/contracts/* cross-plugin contracts (compliance + iterate); adopt-bridge + boundary_coverage_report refactor) | 2026-05-26 |

## Recovery

- **Pipeline**: 1 phases completed
- **Total work events**: 64
- **Last iterate**: change — Refresh docs/guide.md and README.md with Campaign A/B + ADR-060/061/062/089/090 + F7b + runtime/snapshot split + bloat anti-ratchet hook + plugin-cache drift check (2026-05-27)
- **Resume**: `/shipwright-iterate` for next change, or `/shipwright-run` for new pipeline

## Recent Decisions

### ADR-088: shared/contracts/* — cross-plugin contract surface introduced for compliance + iterate
- **Date:** 2026-05-26
- **Section:** Iterate B8 (Campaign B bloat cleanup) — change: introduce contract package
- **Run-ID:** sub_iterate-20260525-211635-B8
- **Context:** Two callsites used to reach across plugin boundaries via fragile mechanisms: plugins/shipwright-adopt/scripts/lib/compliance_bridge.py spawned update_compliance.py as a subprocess + walked ancestor directories; plugins/shipwright-test/
