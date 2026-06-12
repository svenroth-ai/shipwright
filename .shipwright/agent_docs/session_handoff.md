---
canon_generated: true
run_id: "iterate-2026-06-12-union-curated-agent-docs"
phase: "iterate"
reason: "iterate completion: iterate-2026-06-12-union-curated-agent-docs"
timestamp: "2026-06-12T13:48:53.414596+00:00"
---

# Session Handoff

> Auto-generated 2026-06-12 13:48:53 UTC

## Session Info

- **Session ID**: e40d1082-2df5-473b-853e-641d52bef467
- **Timestamp**: 2026-06-12 13:48:53 UTC
- **Reason**: iterate completion: iterate-2026-06-12-union-curated-agent-docs

## Last Iterate

- **Run ID**: iterate-2026-06-12-automerge-serial-integrate
- **Date**: 2026-06-12T12:06:56.133851Z
- **Type**: change
- **Complexity**: medium
- **Branch**: iterate/automerge-serial-integrate
- **ADR**: iterate-2026-06-12-automerge-serial-integrate
- **Tests passed**: True
- **Spec**: .shipwright/planning/iterate/2026-06-12-automerge-serial-integrate.md

## Current Iterate Progress

- **Branch**: iterate/union-curated-agent-docs
- **Run ID**: iterate-2026-06-12-union-curated-agent-docs
- **Spec**: .shipwright/planning/iterate/2026-06-12-union-curated-agent-docs.md
- **Complexity**: medium (modifies a load-bearing merge abstraction + scaffolds into all managed repos)
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

- **Branch**: iterate/union-curated-agent-docs
- **Last Commit**: 6a3b4b0e fix(triage): union-residence GC recompute + source-derived drift meta-test (a1-6/F19 follow-up) (#208)
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
| evt-3b9f4640 | work_completed | iterate (merge=union for curated agent-docs (architecture.md + conventions.md) via a distinct CURATED_DOC_UNION_PATHS category; closes the parallel-iterate bullet-prepend cascade server-side (follow-up to automerge-serial-integrate).) | 2026-06-12 |
| evt-ef0a3a15 | work_completed | iterate (Serial integrate_main merge for campaign/parallel iterates: ensure_current.py refresh-if-behind guard at F11 + SHIPWRIGHT_ITERATE_AUTOMERGE defer with serial drain (auto-merge churn fix, Option A).) | 2026-06-12 |
| evt-34fd26e4 | work_completed | iterate (Consolidate the project-detection predicate across all hooks onto one canonical lib.project_root.is_shipwright_project) | 2026-06-12 |
| evt-d67b8b50 | work_completed | iterate (config-reader BOM tolerance (read_config utf-8-sig) + integrate_main commit-failure branch tests; split two at-limit test modules under 300 LOC) | 2026-06-12 |
| evt-16059cc5 | work_completed | iterate (compress agent-doc backlog to one-line pointers + retire convention-routing fallback + lower entry-budget cutoff) | 2026-06-12 |

## Recovery

- **Pipeline**: 1 phases completed
- **Total work events**: 158
- **Last iterate**: change — merge=union for curated agent-docs (architecture.md + conventions.md) via a distinct CURATED_DOC_UNION_PATHS category; closes the parallel-iterate bullet-prepend cascade server-side (follow-up to automerge-serial-integrate). (2026-06-12)
- **Resume**: `/shipwright-iterate` for next change, or `/shipwright-run` for new pipeline

## Recent Decisions

### ADR-142: Extract drift_anchor.py; resolve_project_root() in 5 hooks
- **Date:** 2026-06-12
- **Section:** Iterate a1-2 (WP5) - hook resolver canon
- **Context:** WP5 deep-audit: 5 hooks resolve project root wrongly or skip the Shipwright-project guard (F5 os.getcwd fail-open, F6 worktree-prefix, F7 no project guard, F8 abs-path dedup key, F10 counter reader divergence).
- **Decision:** Swap os.getcwd()->resolve_project_root() in the 2 compliance gates + 2 counter readers; strip .worktrees/<slug>/ in
