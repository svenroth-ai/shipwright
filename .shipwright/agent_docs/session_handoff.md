---
canon_generated: true
run_id: "iterate-2026-08-10-i2-test-evidence-phase-source-contract"
phase: "iterate"
reason: "iterate: I2 phase source contract"
timestamp: "2026-08-10T10:44:43.260693+00:00"
---

# Session Handoff

> Auto-generated 2026-08-10 10:44:43 UTC

## Session Info

- **Session ID**: unknown
- **Timestamp**: 2026-08-10 10:44:43 UTC
- **Reason**: iterate: I2 phase source contract

## Last Iterate

- **Run ID**: iterate-2026-08-10-i2-test-evidence-phase-source-contract
- **Date**: 2026-08-10T10:44:43.052372Z
- **Type**: bug
- **Complexity**: medium
- **Branch**: iterate/i2-test-evidence-phase-source-contract
- **ADR**: iterate-2026-08-10-i2-test-evidence-phase-source-contract
- **Tests passed**: True
- **Spec**: .shipwright/planning/iterate/iterate-2026-08-10-i2-test-evidence-phase-source-contract.md

## Current Iterate Progress

- **Branch**: iterate/i2-test-evidence-phase-source-contract
- **Run ID**: `iterate-2026-08-10-i2-test-evidence-phase-source-contract`
- **Spec**: .shipwright/planning/iterate/iterate-2026-08-10-i2-test-evidence-phase-source-contract.md
- **Complexity**: medium — a shared verifier and a compliance producer must share one serialized phase-source contract.
- **External Review Marker**: missing
- **Review Cascade**: unreadable (unsafe run_id '`iterate-2026-08-10-i2-test-evidence-phase-source-contract`' — must be a single path component (letters, digits, dot, dash, underscore))

### Mandatory replay on Resume

Before dispatching to the handoff's Remaining phase, run these if missing:
- reviews.json is unreadable — investigate before resuming (unsafe run_id '`iterate-2026-08-10-i2-test-evidence-phase-source-contract`' — must be a single path component (letters, digits, dot, dash, underscore))
- Finalization (F0–F11) after all mandatory phases pass

## Legacy build state

- **Phase**: design
- **Current Split**: 01-adopted
- **Current Section**: adopted-baseline

- **Splits**: 0/1 complete
- **Sections**: 0/1 complete

## Git State

- **Branch**: iterate/i2-test-evidence-phase-source-contract
- **Last Commit**: 450d4fee fix(compliance): verify test evidence by phase source
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
| evt-d17b628b | work_completed | iterate (Replace I2 mtime freshness with phase-run provenance and enforce Decision-Drop scanner findings.) | 2026-08-10 |
| evt-36c592ee | work_completed | iterate (Introduce a lifecycle-aware compliance-audit runner with three explicit authority scopes (branch_feedback/merge/release), separating the Stop hook local diagnostics from the global compliance backlog write authority reserved for delivered merge and verified release commits.) | 2026-08-10 |
| evt-de30181b | work_completed | iterate (Replaced authorship exemption with exact-head approval and review-record evidence.) | 2026-08-09 |
| evt-d77ccdd2 | work_completed | iterate (Add docs/token-cost-controllable.md: threshold-based guide (trigger/symptom/action per band) for keeping session/token cost controllable as decision history and session length grow; link from guide.md Ch.9 + Appendix B and README) | 2026-08-09 |
| evt-0bbcf4b6 | work_completed | iterate (Expose outbox-only amend delivery independently from append and status delivery.) | 2026-08-09 |

## Recovery

- **Pipeline**: 1 phases completed
- **Total work events**: 526
- **Last iterate**: bug — Replace I2 mtime freshness with phase-run provenance and enforce Decision-Drop scanner findings. (2026-08-10)
- **Resume**: `/shipwright-iterate` for next change, or `/shipwright-run` for new pipeline

## Recent Decisions

### ADR-347: A third append-only event kind for the triage store
- **Date:** 2026-08-08
- **Section:** Iterate — feature: triage amend event
- **Run-ID:** iterate-2026-08-08-triage-amend-event
- **Context:** triage.jsonl had only append/status; correcting title/detail/severity/kind required dismiss-and-re-file, breaking cross-references. Measured 2026-08-05/07: ~30 cards/week re-filed for content-identical corrections.
- **Decision:** Add a third append-only event kind, amend, folded into read_all_items
