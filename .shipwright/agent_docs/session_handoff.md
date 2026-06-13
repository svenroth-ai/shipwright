---
canon_generated: true
run_id: "iterate-2026-06-13-shc-git-helpers"
phase: "iterate"
reason: "campaign serial drain: 2026-06-13-shared-helper-consolidation/C"
timestamp: "2026-06-13T16:29:51.426705+00:00"
---

# Session Handoff

> Auto-generated 2026-06-13 16:29:51 UTC

## Session Info

- **Session ID**: 1c1c6790-3768-47d0-bd4f-f7a4ed24bee9
- **Timestamp**: 2026-06-13 16:29:51 UTC
- **Reason**: campaign serial drain: 2026-06-13-shared-helper-consolidation/C

## Last Iterate

- **Run ID**: iterate-2026-06-13-unify-simplify-reducibility
- **Date**: 2026-06-13T16:29:51.868315Z
- **Type**: change
- **Complexity**: medium
- **Branch**: iterate/unify-simplify-reducibility
- **ADR**: iterate-2026-06-13-unify-simplify-reducibility
- **Tests passed**: True
- **Spec**: .shipwright/planning/iterate/2026-06-13-unify-simplify-reducibility.md

## Current Iterate Progress

- **Branch**: iterate/2026-06-13-shc-git-helpers
- **External Review Marker**: completed (external_review_state.json @ 2026-06-13T16:20:48)

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

- **Branch**: iterate/2026-06-13-shc-git-helpers
- **Last Commit**: 06840572 Merge remote-tracking branch 'origin/main' into iterate/2026-06-13-shc-git-helpers
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
| evt-751a4ac4 | work_completed | iterate (Fold spec_checks _run_git/_git_available onto verifiers/git_helpers.py (optional timeout param, unified failure code)) | 2026-06-13 |
| evt-ac75c147 | work_completed | iterate (iterate finalization) | 2026-06-13 |
| evt-29a5f711 | work_completed | iterate (Extract duplicated cross-platform _FileLock into shared/scripts/lib/file_lock.py; both call sites import it; unify on the parent-dir-creating superset.) | 2026-06-13 |
| evt-0862b6bc | work_completed | iterate (unify the code-simplify gate with the bloat/reducibility catalog: relocate behavior_snapshot.py to shared/scripts/tools (SSoT), F-simplify adopts the catalog vocabulary, catalog cites the snapshot/verify gate as the mechanical G3 proof) | 2026-06-13 |
| evt-0c568942 | work_completed | iterate (Align the bloat marker writer (check_file_size) to key delta/was_in_allowlist off the worktree's own baseline via a shared worktree_root_for SSoT also used by the Stop gate (trg-537334f1).) | 2026-06-13 |

## Recovery

- **Pipeline**: 1 phases completed
- **Total work events**: 185
- **Last iterate**: change — Fold spec_checks _run_git/_git_available onto verifiers/git_helpers.py (optional timeout param, unified failure code) (2026-06-13)
- **Resume**: `/shipwright-iterate` for next change, or `/shipwright-run` for new pipeline

## Recent Decisions

### ADR-209: Fold spec_checks git wrappers onto verifiers/git_helpers.py
- **Date:** 2026-06-13
- **Section:** Iterate → 2026-06-13-shc-git-helpers (campaign 2026-06-13-shared-helper-consolidation, sub-iterate C)
- **Context:** spec_checks.py re-defined _run_git/_git_available though verifiers/git_helpers.py already provided them; the two _run_git variants differed (timeout=/cwd= and -1 vs 1 failure code) — a reducibility D/A duplication finding.
- **Decision:** Added an optional timeout param (forwarde
