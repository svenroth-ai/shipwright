---
canon_generated: true
run_id: "changelog-v0.23.1-20260602"
phase: "changelog"
reason: "release v0.23.1"
timestamp: "2026-06-02T09:43:00.857693+00:00"
---

# Session Handoff

> Auto-generated 2026-06-02 09:43:00 UTC

## Session Info

- **Session ID**: 42feb775-7101-4888-a0d2-4d2c54ddc665
- **Timestamp**: 2026-06-02 09:43:00 UTC
- **Reason**: release v0.23.1

## Last Iterate

- **Run ID**: iterate-2026-06-02-sessionstart-dedup-guard
- **Date**: 2026-06-02T09:43:20.373798Z
- **Type**: change
- **Complexity**: small
- **Branch**: iterate/sessionstart-dedup-guard
- **ADR**: iterate-2026-06-02-sessionstart-dedup-guard
- **Tests passed**: True

## Legacy build state

- **Phase**: design
- **Current Split**: 01-adopted
- **Current Section**: adopted-baseline

- **Splits**: 0/1 complete
- **Sections**: 0/1 complete

## Git State

- **Branch**: main
- **Last Commit**: f75a0390 fix(hooks): dedup SessionStart Phase-Quality injection to once-per-event (#140)
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
| evt-7e4caba4 | work_completed | iterate (Dedup SessionStart Phase-Quality injection to once-per-event via event_once.claim_once (fail-open).) | 2026-06-02 |
| evt-61e60d2f | work_completed | iterate (Rewrote test_upload_sarif_action_used to assert the real upload-sarif uses: line (anchored regex, version-agnostic) instead of matching a stale comment; corrected the two @v3 permission comments in security.yml to @v4.) | 2026-06-01 |
| evt-e40d7f38 | work_completed | iterate (Pinned third-party GitHub Actions (setup-uv, create-or-update-comment) to commit SHAs; added SHA256 verification for the Gitleaks binary download in ci.yml + security.yml; corrected stale SECURITY.md scope (webui) and Dependabot wording.) | 2026-06-01 |
| evt-904cb041 | work_completed | iterate (Detective audit honors event_amended corrections (group_d applies shared apply_amendments SSOT before D1-D5; new shared/scripts/lib/events_amend.py, re-exported by config.py); D4 disabled for the framework monorepo (gating-CI stale-noise); evt-5aca940d corrected to spec_impact=none.) | 2026-06-01 |
| evt-57e2fbbb | event_amended | — | 2026-06-01 |

## Recovery

- **Pipeline**: 1 phases completed
- **Total work events**: 92
- **Last iterate**: change — Dedup SessionStart Phase-Quality injection to once-per-event via event_once.claim_once (fail-open). (2026-06-02)
- **Resume**: `/shipwright-iterate` for next change, or `/shipwright-run` for new pipeline

## Recent Decisions

### ADR-120: Dedup SessionStart Phase-Quality injection to once-per-event
- **Date:** 2026-06-02
- **Section:** SessionStart hook (shared/scripts/hooks/capture_session_id.py)
- **Run-ID:** iterate-2026-06-02-sessionstart-dedup-guard
- **Context:** capture_session_id.py is registered as a SessionStart hook in all 12 plugins; Claude Code fires every registered hook with no active-plugin filter, so one SessionStart event ran the Phase-Quality Tier-1 FAIL injection ~12x with the identical block (observed li
