---
canon_generated: true
run_id: "iterate-2026-06-16-brand-tagline-opening"
phase: "iterate"
reason: "iterate: brand tagline + agentic-engineering framing in README/guide openings"
timestamp: "2026-06-16T20:39:48.683899+00:00"
---

# Session Handoff

> Auto-generated 2026-06-16 20:39:48 UTC

## Session Info

- **Session ID**: 44a9cd49-1896-4ee5-8591-ed918170e8e0
- **Timestamp**: 2026-06-16 20:39:48 UTC
- **Reason**: iterate: brand tagline + agentic-engineering framing in README/guide openings

## Last Iterate

- **Run ID**: iterate-2026-06-16-guide-remove-provenance-refs
- **Date**: 2026-06-16T20:12:41.330694Z
- **Type**: change
- **Complexity**: small
- **Branch**: iterate/guide-remove-provenance-refs
- **ADR**: iterate-2026-06-16-guide-remove-provenance-refs
- **Tests passed**: True

## Current Iterate Progress

- **Branch**: iterate/brand-tagline-opening
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

- **Branch**: iterate/brand-tagline-opening
- **Last Commit**: b6b5e8a4 docs(guide): remove development-provenance references (#256)
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
| evt-61e7068b | work_completed | iterate (Lead README and guide openings with the brand tagline 'Ship right, not just fast.' and the vibe-coding-to-agentic-engineering positioning) | 2026-06-16 |
| evt-0dcddd3a | work_completed | iterate (Remove development-provenance references (ADRs, iterate IDs, version/campaign stamps) from docs/guide.md so it documents current behavior, not its origin history) | 2026-06-16 |
| evt-873c69a9 | work_completed | iterate (tighten bloat baseline for iterate_checks.py (1122->1121)) | 2026-06-15 |
| evt-5fb3dfc0 | work_completed | iterate (SessionStart phase-quality consumer drops sentinel-run (run_id unknown) FAILs from a stale findings digest and caps AFTER filtering; raw parser left uncapped. Defense-in-depth mirroring load_actionable_findings.) | 2026-06-15 |
| evt-1ee82e4f | work_completed | iterate (Repo-agnostic agent-doc entry-budget gate (lib.agent_doc_budget + check_agent_doc_budget.py + F11 verifier check), closed the run-id-slug date hole, fixed the blank-line ADR writer, and compacted/de-bolded architecture.md + conventions.md.) | 2026-06-14 |

## Recovery

- **Pipeline**: 1 phases completed
- **Total work events**: 198
- **Last iterate**: change — Lead README and guide openings with the brand tagline 'Ship right, not just fast.' and the vibe-coding-to-agentic-engineering positioning (2026-06-16)
- **Resume**: `/shipwright-iterate` for next change, or `/shipwright-run` for new pipeline

## Recent Decisions

### ADR-225: Tighten iterate_checks.py bloat-baseline entry to actual LOC
- **Date:** 2026-06-15
- **Section:** Iterate — change: tighten bloat baseline
- **Run-ID:** iterate-2026-06-15-tighten-bloat-baseline
- **Context:** Group-H2 detective audit flagged shipwright_bloat_baseline.json as over-recording shared/scripts/tools/verifiers/iterate_checks.py at 1122 lines while the file is 1121 — a prior iterate trimmed one line and never re-tightened the baseline.
- **Decision:** Lower the entry's current fr
