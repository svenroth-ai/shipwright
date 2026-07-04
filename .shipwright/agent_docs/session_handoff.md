---
canon_generated: true
run_id: "iterate-2026-07-04-pr-review-exclude-generated-diff"
phase: "iterate"
reason: "iterate: pr_review exclude generated diff"
timestamp: "2026-07-04T08:48:55.047991+00:00"
---

# Session Handoff

> Auto-generated 2026-07-04 08:48:55 UTC

## Session Info

- **Session ID**: d6ce5fc1-f421-4efb-8fb5-a04215b1284a
- **Timestamp**: 2026-07-04 08:48:55 UTC
- **Reason**: iterate: pr_review exclude generated diff

## Last Iterate

- **Run ID**: iterate-2026-07-04-grade-g2-review-followup
- **Date**: 2026-07-04T08:03:21.905911Z
- **Type**: bug
- **Complexity**: small
- **Branch**: iterate/grade-g2-review-followup
- **ADR**: iterate-2026-07-04-grade-g2-review-followup
- **Tests passed**: True

## Current Iterate Progress

- **Branch**: iterate/pr-review-exclude-generated-diff
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

- **Branch**: iterate/pr-review-exclude-generated-diff
- **Last Commit**: d7224006 chore(triage): sweep 2 outbox append(s) into branch
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
| evt-f166acab | work_completed | iterate (Tier-3 pr_review filters producer-generated file-sections (compliance/agent-docs/lockfiles/state-logs) out of the diff before the truncation check, with the excluded list disclosed in PR meta + comment) | 2026-07-04 |
| evt-443a5258 | work_completed | iterate (shipwright-grade G2 external-review follow-up: tier-2 test-check precision (drop build/ci false positives) + code-scanning ref URL-encoding + full-report byte-identical golden + SARIF-JSON clarification) | 2026-07-04 |
| evt-cb7cb6b8 | work_completed | iterate (shipwright-grade G2: light security, dependency, maintainability and network-gated test-health signals for cold repos) | 2026-07-04 |
| evt-feb2ef5e | work_completed | iterate (shipwright-grade G1: cold-repo signal projector (new read-only plugin)) | 2026-07-03 |
| evt-9d089d93 | work_completed | iterate (Producer-side accepted-risk Semgrep rule tailoring: two opt-in default-off env channels (wholesale exact check_id; owner-scoped mutable-tag via file-read) stop the weekly self-scan re-surfacing 14 dependabot-cooldown + 12 GitHub-owned mutable-tag findings; unpinned third-party actions stay flagged.) | 2026-07-03 |

## Recovery

- **Pipeline**: 1 phases completed
- **Total work events**: 247
- **Last iterate**: change — Tier-3 pr_review filters producer-generated file-sections (compliance/agent-docs/lockfiles/state-logs) out of the diff before the truncation check, with the excluded list disclosed in PR meta + comment (2026-07-04)
- **Resume**: `/shipwright-iterate` for next change, or `/shipwright-run` for new pipeline

## Recent Decisions

### ADR-235: Dedup the bloat-gate Stop block across the plugin fan-out
- **Date:** 2026-06-20
- **Section:** shared/scripts/hooks/bloat_gate_on_stop.py
- **Run-ID:** iterate-2026-06-20-bloat-gate-stop-fanout-dedup
- **Context:** The bloat gate is registered in all 12 plugins, so one Stop event fires it 12x. PR #250 (hook-fanout-dedup) guarded audit/handoff/drift but listed bloat_gate_on_stop as 'already convergent' — wrong: its empty pass path is invisible, masking that the BLOCK path re-emits the full 
