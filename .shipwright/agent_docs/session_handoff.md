---
canon_generated: true
run_id: "iterate-2026-06-28-ar10-sarif-ingestion"
phase: "iterate"
reason: "AR-10 SARIF-ingestion fallback for adopted repos"
timestamp: "2026-06-28T20:55:31.664132+00:00"
---

# Session Handoff

> Auto-generated 2026-06-28 20:55:31 UTC

## Session Info

- **Session ID**: d0a3ca22-cdbd-40bd-a869-8350a27c3c1b
- **Timestamp**: 2026-06-28 20:55:31 UTC
- **Reason**: AR-10 SARIF-ingestion fallback for adopted repos

## Last Iterate

- **Run ID**: iterate-2026-06-28-grade-anchor-maint-wording
- **Date**: 2026-06-28T19:59:34.944428Z
- **Type**: change
- **Complexity**: trivial
- **Branch**: iterate/grade-anchor-maint-wording
- **ADR**: iterate-2026-06-28-grade-anchor-maint-wording
- **Tests passed**: True

## Current Iterate Progress

- **Branch**: iterate/ar10-sarif-ingestion
- **External Review Marker**: missing

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

- **Branch**: iterate/ar10-sarif-ingestion
- **Last Commit**: e96a989a fix(compliance): maintainability grade anchor describes the check, not the label (#290)
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
| evt-f8975c35 | work_completed | iterate (AR-10 SARIF-ingestion fallback in shared github_api.py: when the security-scan-results artifact has no findings.json (every /shipwright-adopt repo runs the SARIF-only scanner template), parse sarif/*.sarif into severity-bucketed findings (security-severity CVSS bands; gitleaks->critical). findings.json stays authoritative when present (empty list never falls through). So the Control-Grade Security dimension lights for adopted repos, not just the monorepo. +6 unit tests; real-webui-SARIF probe parsed 165 findings (135 low / 24 medium / 6 high).) | 2026-06-28 |
| evt-0bcce391 | work_completed | iterate (Control-Grade maintainability anchor describes the check (no unchecked code-size growth) instead of repeating the dimension label) | 2026-06-28 |
| evt-2d2828bd | work_completed | iterate (Refresh ci-security.json + dashboard from the post-#272 clean CI scan (0 high/critical) -> Control Grade A 90 -> A 100/100.) | 2026-06-28 |
| evt-75761dd3 | work_completed | iterate (Control-Grade anchors: plain-language + open-standard-only (drop SonarQube), English methodology note, guide dimensions table) | 2026-06-28 |
| evt-a0fb4818 | work_completed | iterate (AR-05: RTM Reconciled? column + readability (consumes BP-2)) | 2026-06-28 |

## Recovery

- **Pipeline**: 1 phases completed
- **Total work events**: 225
- **Last iterate**: change — AR-10 SARIF-ingestion fallback in shared github_api.py: when the security-scan-results artifact has no findings.json (every /shipwright-adopt repo runs the SARIF-only scanner template), parse sarif/*.sarif into severity-bucketed findings (security-severity CVSS bands; gitleaks->critical). findings.json stays authoritative when present (empty list never falls through). So the Control-Grade Security dimension lights for adopted repos, not just the monorepo. +6 unit tests; real-webui-SARIF probe parsed 165 findings (135 low / 24 medium / 6 high). (2026-06-28)
- **Resume**: `/shipwright-iterate` for next change, or `/shipwright-run` for new pipeline

## Recent Decisions

### ADR-235: Dedup the bloat-gate Stop block across the plugin fan-out
- **Date:** 2026-06-20
- **Section:** shared/scripts/hooks/bloat_gate_on_stop.py
- **Run-ID:** iterate-2026-06-20-bloat-gate-stop-fanout-dedup
- **Context:** The bloat gate is registered in all 12 plugins, so one Stop event fires it 12x. PR #250 (hook-fanout-dedup) guarded audit/handoff/drift but listed bloat_gate_on_stop as 'already convergent' — wrong: its empty pass path is invisible, masking that the BLOCK path re-emits the full 
