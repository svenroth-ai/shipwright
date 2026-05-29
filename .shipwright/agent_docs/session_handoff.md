---
canon_generated: true
run_id: "iterate-2026-05-29-fix-path-canon-allowlist"
phase: "iterate"
reason: "iterate: refresh artifact-path-canon allowlist"
timestamp: "2026-05-28T22:31:54.970539+00:00"
---

# Session Handoff

> Auto-generated 2026-05-28 22:31:54 UTC

## Session Info

- **Session ID**: 37e2bfe1-a0ee-4002-8a52-4b7fd1e0da0a
- **Timestamp**: 2026-05-28 22:31:54 UTC
- **Reason**: iterate: refresh artifact-path-canon allowlist

## Last Iterate

- **Run ID**: iterate-2026-05-27-guide-readme-refresh
- **Date**: 2026-05-27T20:45:59.698617Z
- **Type**: change
- **Complexity**: medium
- **Branch**: iterate/guide-readme-refresh
- **ADR**: iterate-2026-05-27-guide-readme-refresh
- **Tests passed**: True
- **Spec**: .shipwright/planning/iterate/proposed-guide-readme-refresh.md

## Current Iterate Progress

- **Branch**: iterate/fix-path-canon-allowlist
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

- **Branch**: iterate/fix-path-canon-allowlist
- **Last Commit**: c78fd14 docs(agent-docs): add guide-readme-refresh to architecture baseline
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
| evt-4244f6e9 | work_completed | iterate (Refresh artifact-path-canon ALLOWLIST for Campaign A/B aftermath (41 legitimate findings)) | 2026-05-28 |
| evt-d15e38c0 | work_completed | iterate (Correction event: spec_impact=none with proper justification field for the verifier (supersedes evt-13153a5c).) | 2026-05-27 |
| evt-13153a5c | work_completed | iterate (Refresh docs/guide.md and README.md with Campaign A/B + ADR-060/061/062/089/090 + F7b + runtime/snapshot split + bloat anti-ratchet hook + plugin-cache drift check) | 2026-05-27 |
| evt-536e20a7 | work_completed | iterate (Refresh SBOM after syncing dev extras across plugin workspaces; clears 4 stale triage entries (pytest/pytest-mock now resolve as MIT)) | 2026-05-27 |
| evt-bf6d663c | work_completed | iterate (Correction event: spec_impact reclassified to none with justification (supersedes evt-5aca940d).) | 2026-05-27 |

## Recovery

- **Pipeline**: 1 phases completed
- **Total work events**: 66
- **Last iterate**: bug — Refresh artifact-path-canon ALLOWLIST for Campaign A/B aftermath (41 legitimate findings) (2026-05-28)
- **Resume**: `/shipwright-iterate` for next change, or `/shipwright-run` for new pipeline

## Recent Decisions

### ADR-088: shared/contracts/* — cross-plugin contract surface introduced for compliance + iterate
- **Date:** 2026-05-26
- **Section:** Iterate B8 (Campaign B bloat cleanup) — change: introduce contract package
- **Run-ID:** sub_iterate-20260525-211635-B8
- **Context:** Two callsites used to reach across plugin boundaries via fragile mechanisms: plugins/shipwright-adopt/scripts/lib/compliance_bridge.py spawned update_compliance.py as a subprocess + walked ancestor directories; plugins/shipwright-test/
