---
canon_generated: true
run_id: "iterate-2026-06-29-compliance-exempt-not-deficit"
phase: "iterate"
reason: "iterate: compliance exempt != deficit"
timestamp: "2026-06-29T07:44:01.619236+00:00"
---

# Session Handoff

> Auto-generated 2026-06-29 07:44:01 UTC

## Session Info

- **Session ID**: 1d0408e4-4f23-4d3b-9deb-33139d432694
- **Timestamp**: 2026-06-29 07:44:01 UTC
- **Reason**: iterate: compliance exempt != deficit

## Last Iterate

- **Run ID**: iterate-2026-06-28-ar10-sarif-ingestion
- **Date**: 2026-06-28T20:56:27.850346Z
- **Type**: change
- **Complexity**: small
- **Branch**: iterate/ar10-sarif-ingestion
- **ADR**: iterate-2026-06-28-ar10-sarif-ingestion
- **Tests passed**: True

## Current Iterate Progress

- **Branch**: iterate/compliance-exempt-not-deficit
- **Run ID**: iterate-2026-06-29-compliance-exempt-not-deficit
- **Spec**: .shipwright/planning/iterate/2026-06-29-compliance-exempt-not-deficit.md
- **Complexity**: medium
- **External Review Marker**: missing

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

- **Branch**: iterate/compliance-exempt-not-deficit
- **Last Commit**: 27e1251b feat(compliance): AR-10 SARIF-ingestion fallback so adopted repos light the Security dimension (#291)
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
| evt-83b58b36 | work_completed | iterate (Compliance producers stop flagging legitimately-exempt items as deficits: grandfathered bloat over-limit renders INFO (ratchet delta stays the WARN), the iterate-tests denominator excludes satisfied-no-FR changes, audit Suggested lines emit only on FAIL, and routine regens stamp a churn-free staleness banner on audit-report.md.) | 2026-06-29 |
| evt-f8975c35 | work_completed | iterate (AR-10 SARIF-ingestion fallback in shared github_api.py: when the security-scan-results artifact has no findings.json (every /shipwright-adopt repo runs the SARIF-only scanner template), parse sarif/*.sarif into severity-bucketed findings (security-severity CVSS bands; gitleaks->critical). findings.json stays authoritative when present (empty list never falls through). So the Control-Grade Security dimension lights for adopted repos, not just the monorepo. +6 unit tests; real-webui-SARIF probe parsed 165 findings (135 low / 24 medium / 6 high).) | 2026-06-28 |
| evt-0bcce391 | work_completed | iterate (Control-Grade maintainability anchor describes the check (no unchecked code-size growth) instead of repeating the dimension label) | 2026-06-28 |
| evt-2d2828bd | work_completed | iterate (Refresh ci-security.json + dashboard from the post-#272 clean CI scan (0 high/critical) -> Control Grade A 90 -> A 100/100.) | 2026-06-28 |
| evt-75761dd3 | work_completed | iterate (Control-Grade anchors: plain-language + open-standard-only (drop SonarQube), English methodology note, guide dimensions table) | 2026-06-28 |

## Recovery

- **Pipeline**: 1 phases completed
- **Total work events**: 226
- **Last iterate**: change — Compliance producers stop flagging legitimately-exempt items as deficits: grandfathered bloat over-limit renders INFO (ratchet delta stays the WARN), the iterate-tests denominator excludes satisfied-no-FR changes, audit Suggested lines emit only on FAIL, and routine regens stamp a churn-free staleness banner on audit-report.md. (2026-06-29)
- **Resume**: `/shipwright-iterate` for next change, or `/shipwright-run` for new pipeline

## Recent Decisions

### ADR-235: Dedup the bloat-gate Stop block across the plugin fan-out
- **Date:** 2026-06-20
- **Section:** shared/scripts/hooks/bloat_gate_on_stop.py
- **Run-ID:** iterate-2026-06-20-bloat-gate-stop-fanout-dedup
- **Context:** The bloat gate is registered in all 12 plugins, so one Stop event fires it 12x. PR #250 (hook-fanout-dedup) guarded audit/handoff/drift but listed bloat_gate_on_stop as 'already convergent' — wrong: its empty pass path is invisible, masking that the BLOCK path re-emits the full 
