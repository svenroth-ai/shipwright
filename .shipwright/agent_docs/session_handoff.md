---
canon_generated: true
run_id: "iterate-2026-06-12-utf8-git-tools"
phase: "iterate"
reason: "iterate: UTF-8 git-reading tools (WP7)"
timestamp: "2026-06-12T07:12:54.746171+00:00"
---

# Session Handoff

> Auto-generated 2026-06-12 07:12:54 UTC

## Session Info

- **Session ID**: f1dfbc99-c830-4ef1-9897-9a176d13cf6d
- **Timestamp**: 2026-06-12 07:12:54 UTC
- **Reason**: iterate: UTF-8 git-reading tools (WP7)

## Last Iterate

- **Run ID**: iterate-2026-06-12-triage-status-idle-main-outbox
- **Date**: 2026-06-11T22:33:22.081188Z
- **Type**: change
- **Complexity**: small
- **Branch**: iterate/triage-status-idle-main-outbox
- **ADR**: iterate-2026-06-12-triage-status-idle-main-outbox
- **Tests passed**: True

## Current Iterate Progress

- **Branch**: iterate/audit1-utf8-git-tools
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

- **Branch**: iterate/audit1-utf8-git-tools
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
| evt-683ced86 | work_completed | iterate (Pin UTF-8 on git-reading subprocess decodes (deep-audit WP7 F23/F26/F27)) | 2026-06-12 |
| evt-0cd9ae46 | work_completed | iterate (triage.mark_status routes idle-main status flips to the outbox (symmetric with append_triage_item), completing campaign D1 for the status side; fixes undelivered tracked drift from WebUI/Stop-hook dismisses) | 2026-06-11 |
| evt-860e1092 | work_completed | iterate (F11 arms GitHub-native auto-merge for iterate/* PRs (gh pr merge --auto --squash --delete-branch), branch-scoped + fail-soft (B4.5 Phase 3)) | 2026-06-11 |
| evt-86a0a95c | work_completed | iterate (Tier-3 PR review via OpenRouter custom-script (B4.5 Phase 2): pr-review.yml workflow + pr_review.py reviewer + pr_reviewer prompts + 4 snapshot/unit test files) | 2026-06-11 |
| evt-bb5fc0f9 | work_completed | iterate (Add gh-pr-ci:{pr_number} action-unit: failed hard-gates on open PRs land in triage (B4.5 automerge loop-closing). Differentiated auto-resolve; session-wide symmetry; draft exclusion; truncation + filter=latest guards.) | 2026-06-11 |

## Recovery

- **Pipeline**: 1 phases completed
- **Total work events**: 144
- **Last iterate**: bug — Pin UTF-8 on git-reading subprocess decodes (deep-audit WP7 F23/F26/F27) (2026-06-12)
- **Resume**: `/shipwright-iterate` for next change, or `/shipwright-run` for new pipeline

## Recent Decisions

### ADR-141: Empirical verification gate for the D2 outbox sweep/GC
- **Date:** 2026-06-08
- **Section:** Iterate D2V — outbox-delivery campaign
- **Context:** D3 stacked on D2 (outbox->sweep->GC); a silent triage-line loss in D2 would propagate to every adopted repo via D3. The campaign needs a HARD, non-mocked empirical gate before D3 proceeds.
- **Decision:** Built a real empirical harness (shared/tests/test_d2v_empirical_gate*.py) over the REAL D2 code + real git: 200 thread + 40 cross-process trial
