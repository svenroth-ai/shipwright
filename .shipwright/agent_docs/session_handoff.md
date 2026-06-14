---
canon_generated: true
run_id: "iterate-2026-06-14-campaign-runmodel-docs"
phase: "iterate"
reason: "iterate: campaign run-model docs"
timestamp: "2026-06-14T06:17:50.945901+00:00"
---

# Session Handoff

> Auto-generated 2026-06-14 06:17:50 UTC

## Session Info

- **Session ID**: 7ef46c34-70e9-4721-a56c-11667233ab34
- **Timestamp**: 2026-06-14 06:17:50 UTC
- **Reason**: iterate: campaign run-model docs

## Last Iterate

- **Run ID**: iterate-2026-06-13-campaign-serial-default
- **Date**: 2026-06-13T22:08:53.488643Z
- **Type**: change
- **Complexity**: medium
- **Branch**: iterate/campaign-serial-default
- **ADR**: iterate-2026-06-13-campaign-serial-default
- **Tests passed**: True
- **Spec**: .shipwright/planning/iterate/2026-06-13-campaign-serial-default.md

## Current Iterate Progress

- **Branch**: iterate/campaign-runmodel-docs
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

- **Branch**: iterate/campaign-runmodel-docs
- **Last Commit**: 672416a4 Merge remote-tracking branch 'origin/main'
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
| evt-3bb2acf3 | work_completed | iterate (Document the campaign interleaved-serial run-model in docs/guide.md (new Chapter 8 Campaign Mode section + Appendix B sharpening + stale drain-example fix)) | 2026-06-14 |
| evt-ead63c7f | work_completed | iterate (tighten bloat baseline to actual LOC; prune 3 under-limit entries (clear Group H2)) | 2026-06-13 |
| evt-545e463c | work_completed | iterate (Pin verifier CLI stdout to UTF-8 — fix Windows cp1252 UnicodeEncodeError on '→' in reports) | 2026-06-13 |
| evt-ae982255 | work_completed | iterate (interleaved-serial as the single documented campaign default (branch_strategy: serial)) | 2026-06-13 |
| evt-751a4ac4 | work_completed | iterate (Fold spec_checks _run_git/_git_available onto verifiers/git_helpers.py (optional timeout param, unified failure code)) | 2026-06-13 |

## Recovery

- **Pipeline**: 1 phases completed
- **Total work events**: 190
- **Last iterate**: change — Document the campaign interleaved-serial run-model in docs/guide.md (new Chapter 8 Campaign Mode section + Appendix B sharpening + stale drain-example fix) (2026-06-14)
- **Resume**: `/shipwright-iterate` for next change, or `/shipwright-run` for new pipeline

## Recent Decisions

### ADR-209: Fold spec_checks git wrappers onto verifiers/git_helpers.py
- **Date:** 2026-06-13
- **Section:** Iterate → 2026-06-13-shc-git-helpers (campaign 2026-06-13-shared-helper-consolidation, sub-iterate C)
- **Context:** spec_checks.py re-defined _run_git/_git_available though verifiers/git_helpers.py already provided them; the two _run_git variants differed (timeout=/cwd= and -1 vs 1 failure code) — a reducibility D/A duplication finding.
- **Decision:** Added an optional timeout param (forwarde
