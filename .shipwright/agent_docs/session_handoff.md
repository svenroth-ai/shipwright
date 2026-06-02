---
canon_generated: true
run_id: "iterate-2026-06-02-sessionstart-dedup-guard"
phase: "iterate"
reason: "iterate finalization"
timestamp: "2026-06-02T09:43:00.857693+00:00"
---

# Session Handoff

> Auto-generated 2026-06-02 09:43:00 UTC

## Session Info

- **Session ID**: 42feb775-7101-4888-a0d2-4d2c54ddc665
- **Timestamp**: 2026-06-02 09:43:00 UTC
- **Reason**: iterate finalization

## Last Iterate

- **Run ID**: iterate-2026-06-01-upload-sarif-test-fix
- **Date**: 2026-06-01T21:14:39.534334Z
- **Type**: change
- **Complexity**: trivial
- **Branch**: iterate/upload-sarif-test-fix
- **ADR**: iterate-2026-06-01-upload-sarif-test-fix
- **Tests passed**: True

## Current Iterate Progress

- **Branch**: iterate/sessionstart-dedup-guard
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

- **Branch**: iterate/sessionstart-dedup-guard
- **Last Commit**: f558e068 Merge pull request #139 from svenroth-ai/iterate/upload-sarif-test-fix
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

### ADR-116: Document the gating ruff lint step in CLAUDE.md
- **Date:** 2026-06-01
- **Section:** CLAUDE.md / Development
- **Run-ID:** iterate-2026-06-01-refresh-claudemd-lint-gate
- **Context:** The SessionStart timestamp-drift heuristic flagged CLAUDE.md as stale because pyproject.toml changed more recently; the real delta was the 2026-05-31 CI ruff lint gate (uvx ruff@0.15.15 check . in ci.yml, curated ruleset in [tool.ruff.lint]), which CLAUDE.md documented nowhere.
- **Decision:** Add a 'Lint is 
