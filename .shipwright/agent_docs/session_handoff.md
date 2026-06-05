---
canon_generated: true
run_id: "iterate-2026-06-05-sbom-cluster-stable-identity"
phase: "iterate"
reason: "iterate: SBOM cluster stable identity"
timestamp: "2026-06-05T12:39:52.235518+00:00"
---

# Session Handoff

> Auto-generated 2026-06-05 12:39:52 UTC

## Session Info

- **Session ID**: 474cb900-eabb-46ef-8f55-83f5fd879d5f
- **Timestamp**: 2026-06-05 12:39:52 UTC
- **Reason**: iterate: SBOM cluster stable identity

## Last Iterate

- **Run ID**: iterate-2026-06-05-a5-gate-behavioral-probe
- **Date**: 2026-06-05T12:12:18.666645Z
- **Type**: change
- **Complexity**: medium
- **Branch**: iterate/a5-gate-behavioral-probe
- **ADR**: iterate-2026-06-05-a5-gate-behavioral-probe
- **Tests passed**: True
- **Spec**: .shipwright/planning/iterate/2026-06-05-a5-gate-behavioral-probe.md

## Current Iterate Progress

- **Branch**: iterate/sbom-cluster-stable-id
- **External Review Marker**: completed (external_review_state.json @ 2026-06-01T06:00:50)

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

- **Branch**: iterate/sbom-cluster-stable-id
- **Last Commit**: 86ea7a68 Merge pull request #152 from svenroth-ai/iterate/a5-gate-behavioral-probe
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
| evt-7e3e2dc7 | work_completed | iterate (SBOM cluster dedup-key = signature + manifest_type only (stable id under membership drift)) | 2026-06-05 |
| evt-7f17543a | work_completed | iterate (B7 Rule E: exclude non-functional Conventional-Commit types (build/chore/ci/docs/style/test) from B7 by default (configurable); functional types still flagged. Supersedes the narrow Rule D + kills the ci/docs/chore backfill treadmill.) | 2026-06-05 |
| evt-702f8c5b | work_completed | iterate (Make the bloat marker recorder + Stop gate worktree-aware: strip the .worktrees/<slug>/ prefix for the baseline lookup so a worktree iterate growing an already-baselined file (ADR+bump) is not mis-classified crossing and does not false-block Stop (trg-305e2aab)) | 2026-06-05 |
| evt-bebd144d | work_completed | iterate (gitleaks --report-path - wrote a stray file named - instead of stdout, so the secrets leg silently returned 0 findings everywhere; report now written to a temp file and read back; smoke positive-control converted to ADR-044 CI-gated fail) | 2026-06-05 |
| evt-2c8f0a52 | work_completed | iterate (Enforce the FR-gate on the finalize write-path + accept same-event D3 delivery) | 2026-06-05 |

## Recovery

- **Pipeline**: 1 phases completed
- **Total work events**: 108
- **Last iterate**: change — SBOM cluster dedup-key = signature + manifest_type only (stable id under membership drift) (2026-06-05)
- **Resume**: `/shipwright-iterate` for next change, or `/shipwright-run` for new pipeline

## Recent Decisions

### ADR-120: Dedup SessionStart Phase-Quality injection to once-per-event
- **Date:** 2026-06-02
- **Section:** SessionStart hook (shared/scripts/hooks/capture_session_id.py)
- **Run-ID:** iterate-2026-06-02-sessionstart-dedup-guard
- **Context:** capture_session_id.py is registered as a SessionStart hook in all 12 plugins; Claude Code fires every registered hook with no active-plugin filter, so one SessionStart event ran the Phase-Quality Tier-1 FAIL injection ~12x with the identical block (observed li
