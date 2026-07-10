---
canon_generated: true
run_id: "iterate-2026-07-10-claude-md-invariant-index"
phase: "iterate"
reason: "iterate: CLAUDE.md keep-it-lean rule + net-growth gate"
timestamp: "2026-07-10T09:34:20.841627+00:00"
---

# Session Handoff

> Auto-generated 2026-07-10 09:34:20 UTC

## Session Info

- **Session ID**: 068394d9-9942-4262-a400-b2dd2d36531a
- **Timestamp**: 2026-07-10 09:34:20 UTC
- **Reason**: iterate: CLAUDE.md keep-it-lean rule + net-growth gate

## Last Iterate

- **Run ID**: iterate-2026-07-10-design-gate-feedback-gitignore
- **Date**: 2026-07-10T06:39:40.825332Z
- **Type**: change
- **Complexity**: small
- **Branch**: iterate/design-gate-feedback
- **ADR**: iterate-2026-07-10-design-gate-feedback-gitignore
- **Tests passed**: True

## Current Iterate Progress

- **Branch**: iterate/claude-md-invariant-index
- **Run ID**: iterate-2026-07-10-claude-md-invariant-index
- **Spec**: .shipwright/planning/iterate/2026-07-10-claude-md-invariant-index.md
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

- **Branch**: iterate/claude-md-invariant-index
- **Last Commit**: 3eb4eada chore(triage): sweep 2 outbox append(s) into branch
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
| evt-63a35662 | work_completed | iterate (CLAUDE.md keep-it-lean writing rule in both producers + forward-only 30-line net-growth gate in the agent-doc budget machinery (lib/CLI/F11 verifier)) | 2026-07-10 |
| evt-b2a0eebf | work_completed | iterate (gitignore transient design-feedback rounds + document single-session review-viewer hosting) | 2026-07-10 |
| evt-ce826fca | work_completed | iterate (Anchor plain-language question rule in constitution + both CLAUDE.md producers (template + adopt render) + guide, with mirror/pin tests) | 2026-07-09 |
| evt-d4739959 | work_completed | iterate (SS8 default-flip to single-session finalization) | 2026-07-08 |
| evt-24b6350d | work_completed | iterate (SS7 CLI E2E capstone finalization) | 2026-07-08 |

## Recovery

- **Pipeline**: 1 phases completed
- **Total work events**: 288
- **Last iterate**: change — CLAUDE.md keep-it-lean writing rule in both producers + forward-only 30-line net-growth gate in the agent-doc budget machinery (lib/CLI/F11 verifier) (2026-07-10)
- **Resume**: `/shipwright-iterate` for next change, or `/shipwright-run` for new pipeline

## Recent Decisions

### ADR-309: Single-session pipeline resumability, recovery & observability (SS5)
- **Date:** 2026-07-08
- **Section:** SS5 resumability/recovery + observability
- **Run-ID:** iterate-2026-07-08-ss5-resumability
- **Context:** Single-session runs (mode==single_session) drive the whole pipeline in ONE master conversation (SS3/SS4). If it dies mid-run there was no first-class resume, and no structured observability into the loop's transitions. Multi-session runs must stay on the old path untouched.
- **De
