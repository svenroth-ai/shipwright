---
canon_generated: true
run_id: "iterate-2026-07-10-emit-phase-started"
phase: "iterate"
reason: "iterate: emit phase_started events (M-Pre-1)"
timestamp: "2026-07-10T22:06:35.593529+00:00"
---

# Session Handoff

> Auto-generated 2026-07-10 22:06:35 UTC

## Session Info

- **Session ID**: c6d96e6a-09ff-4e6f-b168-766dfb9d4fa0
- **Timestamp**: 2026-07-10 22:06:35 UTC
- **Reason**: iterate: emit phase_started events (M-Pre-1)

## Last Iterate

- **Run ID**: iterate-2026-07-10-claude-md-invariant-index
- **Date**: 2026-07-10T09:35:16.646748Z
- **Type**: change
- **Complexity**: medium
- **Branch**: iterate/claude-md-invariant-index
- **ADR**: iterate-2026-07-10-claude-md-invariant-index
- **Tests passed**: True
- **Spec**: .shipwright/planning/iterate/2026-07-10-claude-md-invariant-index.md

## Current Iterate Progress

- **Branch**: iterate/campaign-B1-emit-phase-started
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

- **Branch**: iterate/campaign-B1-emit-phase-started
- **Last Commit**: 5b4bd300 feat(iterate): CLAUDE.md keep-it-lean rule + 30-line net-growth gate (#356)
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
| evt-8045591b | work_completed | iterate (Emit phase_started at pipeline phase entry (M-Pre-1)) | 2026-07-10 |
| evt-63a35662 | work_completed | iterate (CLAUDE.md keep-it-lean writing rule in both producers + forward-only 30-line net-growth gate in the agent-doc budget machinery (lib/CLI/F11 verifier)) | 2026-07-10 |
| evt-b2a0eebf | work_completed | iterate (gitignore transient design-feedback rounds + document single-session review-viewer hosting) | 2026-07-10 |
| evt-ce826fca | work_completed | iterate (Anchor plain-language question rule in constitution + both CLAUDE.md producers (template + adopt render) + guide, with mirror/pin tests) | 2026-07-09 |
| evt-d4739959 | work_completed | iterate (SS8 default-flip to single-session finalization) | 2026-07-08 |

## Recovery

- **Pipeline**: 1 phases completed
- **Total work events**: 289
- **Last iterate**: feature — Emit phase_started at pipeline phase entry (M-Pre-1) (2026-07-10)
- **Resume**: `/shipwright-iterate` for next change, or `/shipwright-run` for new pipeline

## Recent Decisions

### ADR-309: Single-session pipeline resumability, recovery & observability (SS5)
- **Date:** 2026-07-08
- **Section:** SS5 resumability/recovery + observability
- **Run-ID:** iterate-2026-07-08-ss5-resumability
- **Context:** Single-session runs (mode==single_session) drive the whole pipeline in ONE master conversation (SS3/SS4). If it dies mid-run there was no first-class resume, and no structured observability into the loop's transitions. Multi-session runs must stay on the old path untouched.
- **De
