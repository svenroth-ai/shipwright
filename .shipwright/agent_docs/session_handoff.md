---
canon_generated: true
run_id: "iterate-2026-06-12-hook-resolver-canon"
phase: "iterate"
reason: "iterate: WP5 hook resolver canon (F5/F6/F7/F8/F10)"
timestamp: "2026-06-12T06:13:00.365682+00:00"
---

# Session Handoff

> Auto-generated 2026-06-12 06:13:00 UTC

## Session Info

- **Session ID**: f1dfbc99-c830-4ef1-9897-9a176d13cf6d
- **Timestamp**: 2026-06-12 06:13:00 UTC
- **Reason**: iterate: WP5 hook resolver canon (F5/F6/F7/F8/F10)

## Last Iterate

- **Run ID**: iterate-2026-06-12-triage-status-idle-main-outbox
- **Date**: 2026-06-11T22:33:22.081188Z
- **Type**: change
- **Complexity**: small
- **Branch**: iterate/triage-status-idle-main-outbox
- **ADR**: iterate-2026-06-12-triage-status-idle-main-outbox
- **Tests passed**: True

## Current Iterate Progress

- **Branch**: iterate/audit1-hook-resolver-canon
- **External Review Marker**: completed (external_review_state.json @ 2026-06-12T06:00:45)

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

- **Branch**: iterate/audit1-hook-resolver-canon
- **Last Commit**: 57ee522e fix(triage): route idle-main status flips to the outbox in mark_status (#198)
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
| evt-4ee0aee8 | work_completed | iterate (WP5 hook project-root/worktree resolvers + project guard (F5/F6/F7/F8/F10)) | 2026-06-12 |
| evt-0cd9ae46 | work_completed | iterate (triage.mark_status routes idle-main status flips to the outbox (symmetric with append_triage_item), completing campaign D1 for the status side; fixes undelivered tracked drift from WebUI/Stop-hook dismisses) | 2026-06-11 |
| evt-860e1092 | work_completed | iterate (F11 arms GitHub-native auto-merge for iterate/* PRs (gh pr merge --auto --squash --delete-branch), branch-scoped + fail-soft (B4.5 Phase 3)) | 2026-06-11 |
| evt-86a0a95c | work_completed | iterate (Tier-3 PR review via OpenRouter custom-script (B4.5 Phase 2): pr-review.yml workflow + pr_review.py reviewer + pr_reviewer prompts + 4 snapshot/unit test files) | 2026-06-11 |
| evt-bb5fc0f9 | work_completed | iterate (Add gh-pr-ci:{pr_number} action-unit: failed hard-gates on open PRs land in triage (B4.5 automerge loop-closing). Differentiated auto-resolve; session-wide symmetry; draft exclusion; truncation + filter=latest guards.) | 2026-06-11 |

## Recovery

- **Pipeline**: 1 phases completed
- **Total work events**: 144
- **Last iterate**: bug — WP5 hook project-root/worktree resolvers + project guard (F5/F6/F7/F8/F10) (2026-06-12)
- **Resume**: `/shipwright-iterate` for next change, or `/shipwright-run` for new pipeline

## Recent Decisions

### ADR-142: Extract drift_anchor.py; resolve_project_root() in 5 hooks
- **Date:** 2026-06-12
- **Section:** Iterate a1-2 (WP5) - hook resolver canon
- **Context:** WP5 deep-audit: 5 hooks resolve project root wrongly or skip the Shipwright-project guard (F5 os.getcwd fail-open, F6 worktree-prefix, F7 no project guard, F8 abs-path dedup key, F10 counter reader divergence).
- **Decision:** Swap os.getcwd()->resolve_project_root() in the 2 compliance gates + 2 counter readers; strip .worktrees/<slug>/ in
