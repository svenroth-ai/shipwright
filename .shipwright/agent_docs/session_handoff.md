---
canon_generated: true
run_id: "iterate-2026-06-12-installer-shell-fixes"
phase: "iterate"
reason: "x"
timestamp: "2026-06-12T08:48:05.654486+00:00"
---

# Session Handoff

> Auto-generated 2026-06-12 08:48:05 UTC

## Session Info

- **Session ID**: f1dfbc99-c830-4ef1-9897-9a176d13cf6d
- **Timestamp**: 2026-06-12 08:48:05 UTC
- **Reason**: x

## Last Iterate

- **Run ID**: iterate-2026-06-12-compliance-gate-coverage
- **Date**: 2026-06-12T05:32:37.279680Z
- **Type**: bug
- **Complexity**: small
- **Branch**: iterate/audit1-compliance-gate-coverage
- **ADR**: iterate-2026-06-12-compliance-gate-coverage
- **Tests passed**: True
- **Spec**: .shipwright/planning/iterate/campaigns/2026-06-10-audit-1-auto/sub-iterates/a1-1-compliance-gate-coverage.md

## Current Iterate Progress

- **Branch**: iterate/audit1-installer-shell-fixes
- **External Review Marker**: completed (external_review_state.json @ 2026-06-12T08:40:35)

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

- **Branch**: iterate/audit1-installer-shell-fixes
- **Last Commit**: 6b16e8f4 fix(compliance): make Group H + S4 FR-preservation gates fire (deep-audit WP3) (#199)
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
| evt-3064a751 | work_completed | iterate (Installer/shell POSIX fixes (deep-audit WP10 F33-F38): set -e prereq counter, uv ~/.local/bin PATH, 13-plugin space-safe alias refresh, python3 resolver, dotenv-parse verify-setup) | 2026-06-12 |
| evt-94515cf2 | work_completed | iterate (Fix two structurally-inert compliance gates (deep-audit WP3): Group H now in run_all default + on-stop coverage gate widened to A-H (F20); S4 FR-preservation join no longer raises TypeError (F21)) | 2026-06-12 |
| evt-0cd9ae46 | work_completed | iterate (triage.mark_status routes idle-main status flips to the outbox (symmetric with append_triage_item), completing campaign D1 for the status side; fixes undelivered tracked drift from WebUI/Stop-hook dismisses) | 2026-06-11 |
| evt-860e1092 | work_completed | iterate (F11 arms GitHub-native auto-merge for iterate/* PRs (gh pr merge --auto --squash --delete-branch), branch-scoped + fail-soft (B4.5 Phase 3)) | 2026-06-11 |
| evt-86a0a95c | work_completed | iterate (Tier-3 PR review via OpenRouter custom-script (B4.5 Phase 2): pr-review.yml workflow + pr_review.py reviewer + pr_reviewer prompts + 4 snapshot/unit test files) | 2026-06-11 |

## Recovery

- **Pipeline**: 1 phases completed
- **Total work events**: 145
- **Last iterate**: bug — Installer/shell POSIX fixes (deep-audit WP10 F33-F38): set -e prereq counter, uv ~/.local/bin PATH, 13-plugin space-safe alias refresh, python3 resolver, dotenv-parse verify-setup (2026-06-12)
- **Resume**: `/shipwright-iterate` for next change, or `/shipwright-run` for new pipeline

## Recent Decisions

### ADR-142: Installer/shell POSIX fixes (deep-audit WP10 F33-F38)
- **Date:** 2026-06-12
- **Section:** iterate-2026-06-12-installer-shell-fixes
- **Context:** The recommended POSIX install path was broken six ways (deep-audit WP10): F33 ((missing++)) aborts install.sh under set -e; F34 uv PATH ~/.cargo/bin vs astral ~/.local/bin; F35 alias omits adopt + stale-alias skip guard; F36 unquoted $REPO_ROOT splits on spaces; F37 bare python aborts where only python3 exists; F38 verify-setup sources .env.loca
