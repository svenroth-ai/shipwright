---
canon_generated: true
run_id: "iterate-2026-06-30-workflow-token-permissions"
phase: "iterate"
reason: "F11 refresh: integrate #300 churn"
timestamp: "2026-06-30T20:26:19.491004+00:00"
---

# Session Handoff

> Auto-generated 2026-06-30 20:26:19 UTC

## Session Info

- **Session ID**: 21cb3b0b-74e2-4d54-b9ee-595f850b42db
- **Timestamp**: 2026-06-30 20:26:19 UTC
- **Reason**: F11 refresh: integrate #300 churn

## Last Iterate

- **Run ID**: iterate-2026-06-30-strip-zwsp-planning-doc
- **Date**: 2026-06-30T20:26:48.157375Z
- **Type**: change
- **Complexity**: trivial
- **Branch**: iterate/strip-zwsp-planning-doc
- **ADR**: iterate-2026-06-30-strip-zwsp-planning-doc
- **Tests passed**: True

## Current Iterate Progress

- **Branch**: iterate/wf-token-perms
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

- **Branch**: iterate/wf-token-perms
- **Last Commit**: f0d483f0 Merge remote-tracking branch 'origin/main' into iterate/wf-token-perms
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
| evt-87d55739 | work_completed | iterate (Strip 2 zero-width-space (U+200B) chars from a planning note to clear a high prompt-injection scanner finding (UNICODE_ZERO_WIDTH_SPACE)) | 2026-06-30 |
| evt-bf0c17a2 | work_completed | iterate (workflow token-permissions hardening) | 2026-06-30 |
| evt-b89652cc | work_completed | iterate (Remove .github/workflows/scorecard.yml + its ci_gate_allowlist entry + the Added changelog drop. Keep the A+C grade work and the Scorecard methodology citation. Token-permissions + pinned-deps + branch-protection tracked as triage.) | 2026-06-30 |
| evt-e1d5bdb0 | work_completed | iterate (Fix the red Scorecard workflow on main: the publish step failed 400 imposter-commit because the action was SHA-pinned; the OpenSSF publish API only verifies official release tags. Pin to @v2.4.3.) | 2026-06-30 |
| evt-cf798241 | work_completed | iterate (RTM Verification Timeline Date column UTC-normalized (utc_date) so it reads monotonically descending across mixed-timezone events; a +02:00 near-midnight event no longer prints a local date one day off its sort position) | 2026-06-30 |

## Recovery

- **Pipeline**: 1 phases completed
- **Total work events**: 234
- **Last iterate**: change — Strip 2 zero-width-space (U+200B) chars from a planning note to clear a high prompt-injection scanner finding (UNICODE_ZERO_WIDTH_SPACE) (2026-06-30)
- **Resume**: `/shipwright-iterate` for next change, or `/shipwright-run` for new pipeline

## Recent Decisions

### ADR-235: Dedup the bloat-gate Stop block across the plugin fan-out
- **Date:** 2026-06-20
- **Section:** shared/scripts/hooks/bloat_gate_on_stop.py
- **Run-ID:** iterate-2026-06-20-bloat-gate-stop-fanout-dedup
- **Context:** The bloat gate is registered in all 12 plugins, so one Stop event fires it 12x. PR #250 (hook-fanout-dedup) guarded audit/handoff/drift but listed bloat_gate_on_stop as 'already convergent' — wrong: its empty pass path is invisible, masking that the BLOCK path re-emits the full 
