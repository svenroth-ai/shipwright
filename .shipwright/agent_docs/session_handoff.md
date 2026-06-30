---
canon_generated: true
run_id: "iterate-2026-06-30-remove-native-scorecard"
phase: "iterate"
reason: "Remove native Scorecard workflow (human-review-centric anchor, wrong for AI-first); capture supply-chain checks as triage"
timestamp: "2026-06-30T19:20:59.443976+00:00"
---

# Session Handoff

> Auto-generated 2026-06-30 19:20:59 UTC

## Session Info

- **Session ID**: 998fb4e1-d677-4d0a-89cf-cec4a7c4a6ee
- **Timestamp**: 2026-06-30 19:20:59 UTC
- **Reason**: Remove native Scorecard workflow (human-review-centric anchor, wrong for AI-first); capture supply-chain checks as triage

## Last Iterate

- **Run ID**: iterate-2026-06-30-scorecard-publish-tag
- **Date**: 2026-06-30T14:51:18.980033Z
- **Type**: change
- **Complexity**: trivial
- **Branch**: iterate/scorecard-publish-tag
- **ADR**: iterate-2026-06-30-scorecard-publish-tag
- **Tests passed**: True

## Current Iterate Progress

- **Branch**: iterate/remove-native-scorecard
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

- **Branch**: iterate/remove-native-scorecard
- **Last Commit**: efca5737 fix(ci): pin ossf/scorecard-action by tag so publish stops failing (#297)
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
| evt-b89652cc | work_completed | iterate (Remove .github/workflows/scorecard.yml + its ci_gate_allowlist entry + the Added changelog drop. Keep the A+C grade work and the Scorecard methodology citation. Token-permissions + pinned-deps + branch-protection tracked as triage.) | 2026-06-30 |
| evt-e1d5bdb0 | work_completed | iterate (Fix the red Scorecard workflow on main: the publish step failed 400 imposter-commit because the action was SHA-pinned; the OpenSSF publish API only verifies official release tags. Pin to @v2.4.3.) | 2026-06-30 |
| evt-cf798241 | work_completed | iterate (RTM Verification Timeline Date column UTC-normalized (utc_date) so it reads monotonically descending across mixed-timezone events; a +02:00 near-midnight event no longer prints a local date one day off its sort position) | 2026-06-30 |
| evt-bcd40c31 | work_completed | iterate (Goodhart-resistant Control Grade: honesty layer caps the headline on the weakest load-bearing control; anchors pivoted to open SE/NIST standards; native scorecard.yml.) | 2026-06-30 |
| evt-ad994b33 | work_completed | iterate (Navigable compliance artifacts (test-evidence + traceability-matrix): linked iterate/(iter) tokens, descending Verification Timeline, FR + commit links, plain-language summary-preferred Event labels, honest synthesized Full-Suite note) | 2026-06-30 |

## Recovery

- **Pipeline**: 1 phases completed
- **Total work events**: 232
- **Last iterate**: change — Remove .github/workflows/scorecard.yml + its ci_gate_allowlist entry + the Added changelog drop. Keep the A+C grade work and the Scorecard methodology citation. Token-permissions + pinned-deps + branch-protection tracked as triage. (2026-06-30)
- **Resume**: `/shipwright-iterate` for next change, or `/shipwright-run` for new pipeline

## Recent Decisions

### ADR-235: Dedup the bloat-gate Stop block across the plugin fan-out
- **Date:** 2026-06-20
- **Section:** shared/scripts/hooks/bloat_gate_on_stop.py
- **Run-ID:** iterate-2026-06-20-bloat-gate-stop-fanout-dedup
- **Context:** The bloat gate is registered in all 12 plugins, so one Stop event fires it 12x. PR #250 (hook-fanout-dedup) guarded audit/handoff/drift but listed bloat_gate_on_stop as 'already convergent' — wrong: its empty pass path is invisible, masking that the BLOCK path re-emits the full 
