---
canon_generated: true
run_id: "iterate-2026-06-16-guide-remove-provenance-refs"
phase: "iterate"
reason: "iterate: remove provenance references from docs/guide.md"
timestamp: "2026-06-16T20:12:09.635271+00:00"
---

# Session Handoff

> Auto-generated 2026-06-16 20:12:09 UTC

## Session Info

- **Session ID**: 44a9cd49-1896-4ee5-8591-ed918170e8e0
- **Timestamp**: 2026-06-16 20:12:09 UTC
- **Reason**: iterate: remove provenance references from docs/guide.md

## Last Iterate

- **Run ID**: iterate-2026-06-15-tighten-bloat-baseline
- **Date**: 2026-06-15T19:45:38.408313Z
- **Type**: change
- **Complexity**: trivial
- **Branch**: iterate/tighten-bloat-baseline
- **ADR**: iterate-2026-06-15-tighten-bloat-baseline
- **Tests passed**: True

## Current Iterate Progress

- **Branch**: iterate/guide-remove-provenance-refs
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

- **Branch**: iterate/guide-remove-provenance-refs
- **Last Commit**: e5b3c84b chore(triage): sweep 1 outbox append(s) into branch
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
| evt-0dcddd3a | work_completed | iterate (Remove development-provenance references (ADRs, iterate IDs, version/campaign stamps) from docs/guide.md so it documents current behavior, not its origin history) | 2026-06-16 |
| evt-873c69a9 | work_completed | iterate (tighten bloat baseline for iterate_checks.py (1122->1121)) | 2026-06-15 |
| evt-5fb3dfc0 | work_completed | iterate (SessionStart phase-quality consumer drops sentinel-run (run_id unknown) FAILs from a stale findings digest and caps AFTER filtering; raw parser left uncapped. Defense-in-depth mirroring load_actionable_findings.) | 2026-06-15 |
| evt-1ee82e4f | work_completed | iterate (Repo-agnostic agent-doc entry-budget gate (lib.agent_doc_budget + check_agent_doc_budget.py + F11 verifier check), closed the run-id-slug date hole, fixed the blank-line ADR writer, and compacted/de-bolded architecture.md + conventions.md.) | 2026-06-14 |
| evt-7b6a70cb | work_completed | iterate (Phase-quality rollups read load_actionable_findings (excludes sentinel run_id=unknown snapshots), so stale/degenerate audits stop driving false Tier-1 surfacing across the triage backlog, SessionStart injection, dashboard and report.) | 2026-06-14 |

## Recovery

- **Pipeline**: 1 phases completed
- **Total work events**: 197
- **Last iterate**: change — Remove development-provenance references (ADRs, iterate IDs, version/campaign stamps) from docs/guide.md so it documents current behavior, not its origin history (2026-06-16)
- **Resume**: `/shipwright-iterate` for next change, or `/shipwright-run` for new pipeline

## Recent Decisions

### ADR-225: Tighten iterate_checks.py bloat-baseline entry to actual LOC
- **Date:** 2026-06-15
- **Section:** Iterate — change: tighten bloat baseline
- **Run-ID:** iterate-2026-06-15-tighten-bloat-baseline
- **Context:** Group-H2 detective audit flagged shipwright_bloat_baseline.json as over-recording shared/scripts/tools/verifiers/iterate_checks.py at 1122 lines while the file is 1121 — a prior iterate trimmed one line and never re-tightened the baseline.
- **Decision:** Lower the entry's current fr
