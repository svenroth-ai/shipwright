---
canon_generated: true
run_id: "iterate-2026-06-13-verifier-utf8-stdout"
phase: "iterate"
reason: "iterate: pin verifier CLI stdout to UTF-8 (Windows cp1252 fix)"
timestamp: "2026-06-13T18:27:14.218699+00:00"
---

# Session Handoff

> Auto-generated 2026-06-13 18:27:14 UTC

## Session Info

- **Session ID**: 6a2f378c-8669-4874-904a-87c4dc84cdf0
- **Timestamp**: 2026-06-13 18:27:14 UTC
- **Reason**: iterate: pin verifier CLI stdout to UTF-8 (Windows cp1252 fix)

## Last Iterate

- **Run ID**: iterate-2026-06-13-verifier-utf8-stdout
- **Date**: 2026-06-13T18:21:00.464356Z
- **Type**: bug
- **Complexity**: small
- **Branch**: iterate/verifier-utf8-stdout
- **ADR**: iterate-2026-06-13-verifier-utf8-stdout
- **Tests passed**: True

## Current Iterate Progress

- **Branch**: iterate/verifier-utf8-stdout
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

- **Branch**: iterate/verifier-utf8-stdout
- **Last Commit**: 0f85ff5b refactor(triage): stop the iterate pipeline from filing triage about current-run work (#243)
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
| evt-545e463c | work_completed | iterate (Pin verifier CLI stdout to UTF-8 — fix Windows cp1252 UnicodeEncodeError on '→' in reports) | 2026-06-13 |
| evt-751a4ac4 | work_completed | iterate (Fold spec_checks _run_git/_git_available onto verifiers/git_helpers.py (optional timeout param, unified failure code)) | 2026-06-13 |
| evt-4393b0bb | work_completed | iterate (Triage not for current-run work — drop plugin-sync + F0.5 triage producers) | 2026-06-13 |
| evt-ac75c147 | work_completed | iterate (iterate finalization) | 2026-06-13 |
| evt-29a5f711 | work_completed | iterate (Extract duplicated cross-platform _FileLock into shared/scripts/lib/file_lock.py; both call sites import it; unify on the parent-dir-creating superset.) | 2026-06-13 |

## Recovery

- **Pipeline**: 1 phases completed
- **Total work events**: 187
- **Last iterate**: bug — Pin verifier CLI stdout to UTF-8 — fix Windows cp1252 UnicodeEncodeError on '→' in reports (2026-06-13)
- **Resume**: `/shipwright-iterate` for next change, or `/shipwright-run` for new pipeline

## Recent Decisions

### ADR-209: Fold spec_checks git wrappers onto verifiers/git_helpers.py
- **Date:** 2026-06-13
- **Section:** Iterate → 2026-06-13-shc-git-helpers (campaign 2026-06-13-shared-helper-consolidation, sub-iterate C)
- **Context:** spec_checks.py re-defined _run_git/_git_available though verifiers/git_helpers.py already provided them; the two _run_git variants differed (timeout=/cwd= and -1 vs 1 failure code) — a reducibility D/A duplication finding.
- **Decision:** Added an optional timeout param (forwarde
