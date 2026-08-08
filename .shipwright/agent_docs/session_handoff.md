---
canon_generated: true
run_id: "changelog-v0.32.0-20260808-224001"
phase: "changelog"
reason: "release v0.32.0"
timestamp: "2026-08-08T20:34:51.172844+00:00"
---

# Session Handoff

> Auto-generated 2026-08-08 20:34:51 UTC

## Session Info

- **Session ID**: 5e606322-4b30-42ed-9e6b-72bfd03df7be
- **Timestamp**: 2026-08-08 20:34:51 UTC
- **Reason**: release v0.32.0

## Last Iterate

- **Run ID**: iterate-2026-08-08-prompt-scan-dynamic-import-fault-test
- **Date**: 2026-08-08T19:53:58.428334Z
- **Type**: change
- **Complexity**: small
- **Branch**: iterate/prompt-scan-dynamic-import-fault-test
- **ADR**: iterate-2026-08-08-prompt-scan-dynamic-import-fault-test
- **Tests passed**: True
- **Spec**: n/a (small complexity, SIMPLIFY sub-mode, spec_impact none)

## Legacy build state

- **Phase**: design
- **Current Split**: 01-adopted
- **Current Section**: adopted-baseline

- **Splits**: 0/1 complete
- **Sections**: 0/1 complete

## Git State

- **Branch**: main
- **Last Commit**: 11e32523 chore(release): v0.32.0
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
| evt-5036a5fd | grade_snapshot | — | 2026-08-08 |
| evt-512679d4 | work_completed | iterate (mandated-load truncation is now declared, not silent (TC3.2)) | 2026-08-08 |
| evt-f32709d0 | work_completed | iterate (iterate: normalize benign __import__ dynamic-import pattern flagged by shipwright-prompt-scan (trg-133f2ca6)) | 2026-08-08 |
| evt-272f228a | grade_snapshot | — | 2026-08-08 |
| evt-390f315f | work_completed | iterate (iterate: fix shipwright_model_config.json review tier (opus, not sonnet)) | 2026-08-08 |

## Recovery

- **Pipeline**: 1 phases completed
- **Total work events**: 513
- **Last iterate**: feature — mandated-load truncation is now declared, not silent (TC3.2) (2026-08-08)
- **Resume**: `/shipwright-iterate` for next change, or `/shipwright-run` for new pipeline

## Recent Decisions

### ADR-347: A third append-only event kind for the triage store
- **Date:** 2026-08-08
- **Section:** Iterate — feature: triage amend event
- **Run-ID:** iterate-2026-08-08-triage-amend-event
- **Context:** triage.jsonl had only append/status; correcting title/detail/severity/kind required dismiss-and-re-file, breaking cross-references. Measured 2026-08-05/07: ~30 cards/week re-filed for content-identical corrections.
- **Decision:** Add a third append-only event kind, amend, folded into read_all_items
