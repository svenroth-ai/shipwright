---
canon_generated: true
run_id: "iterate-2026-05-11-test-hygiene-and-skill-rules"
phase: "iterate"
reason: "iterate: test-hygiene-and-skill-rules"
timestamp: "2026-05-11T08:55:59.110405+00:00"
---

# Session Handoff

> Auto-generated 2026-05-11 08:55:59 UTC

## Session Info

- **Session ID**: 9f3ead4d-f083-49fe-b5d6-d943bed48c4e
- **Timestamp**: 2026-05-11 08:55:59 UTC
- **Reason**: iterate: test-hygiene-and-skill-rules

## Last Iterate

- **Run ID**: iterate-2026-05-10-adopt-ci-scaffolders
- **Date**: 2026-05-10T22:26:32.703599Z
- **Type**: feature
- **Complexity**: large
- **Branch**: iterate/adopt-ci-scaffolders
- **ADR**: ADR-043
- **Tests passed**: True
- **Spec**: .shipwright/planning/iterate/2026-05-10-adopt-ci-scaffolders.md

## Current Iterate Progress

- **Branch**: iterate/test-hygiene-and-skill-rules
- **Run ID**: iterate-2026-05-11-test-hygiene-and-skill-rules
- **Spec**: .shipwright/planning/iterate/2026-05-11-test-hygiene-and-skill-rules.md
- **Complexity**: medium
- **External Review Marker**: stale (predates spec (2026-05-09T07:45:15))

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

- **Branch**: iterate/test-hygiene-and-skill-rules
- **Last Commit**: ad739c1 Merge pull request #24 from svenroth-ai/iterate/adopt-ci-scaffolders
- **Uncommitted Changes**: Yes

## Config Files to Read

- `shipwright_run_config.json` — exists
- `shipwright_project_config.json` — exists
- `shipwright_plan_config.json` — exists
- `shipwright_build_config.json` — exists
- `shipwright_security_config.json` — missing
- `shipwright_compliance_config.json` — exists

## Last Events

| Event | Type | Source | Date |
|-------|------|--------|------|
| evt-c8a57331 | work_completed | iterate (known_issues scanner requires comment context; remove dead save_session_config — 16/16 green) | 2026-05-09 |
| evt-f66286bf | work_completed | iterate (—) | 2026-05-07 |
| evt-623a29ad | work_completed | iterate (—) | 2026-05-07 |
| evt-40c653f7 | work_completed | iterate (F0.5 empirical-test backfill) | 2026-05-06 |
| evt-510b8df3 | work_completed | iterate (F0.5 End-to-End Verification Gate) | 2026-05-06 |

## Recovery

- **Pipeline**: 1 phases completed
- **Total work events**: 24
- **Last iterate**: bug — known_issues scanner requires comment context; remove dead save_session_config — 16/16 green (2026-05-09)
- **Resume**: `/shipwright-iterate` for next change, or `/shipwright-run` for new pipeline

## Recent Decisions

### ADR-044: Silent skips loud-fail in CI + Step 6 governance rules
- **Date:** 2026-05-11
- **Section:** Iterate — change: test-hygiene-and-skill-rules
- **Context:** Six binary-skip sites + 7 cross-plugin import-skip sites in shared/tests + iterate plugin tests were silently masking missing toolchains and sys.path collisions; no SKILL.md rule existed to prevent recurrence. Test infra was greening on no-op tests and missing-binary skips.
- **Decision:** Convert all silent skips to a CI-gated hard-fail 
