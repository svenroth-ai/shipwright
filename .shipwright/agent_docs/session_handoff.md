---
canon_generated: true
run_id: "iterate-2026-09-12-generated-prefixes-provenance-anchor"
phase: "iterate"
reason: "iterate: anchor or remove is_safe_to_skip_review's _GENERATED_PREFIXES skip-safety per prefix"
timestamp: "2026-09-12T06:25:32.512191+00:00"
---

# Session Handoff

> Auto-generated 2026-09-12 06:25:32 UTC

## Session Info

- **Session ID**: 8d134d7c-6358-4d69-9360-d4b362d068d8
- **Timestamp**: 2026-09-12 06:25:32 UTC
- **Reason**: iterate completion: iterate-2026-09-12-generated-prefixes-provenance-anchor

## Last Iterate

- **Run ID**: iterate-2026-09-12-generated-prefixes-provenance-anchor
- **Date**: 2026-09-12T06:25:32.304815Z
- **Type**: bug
- **Complexity**: small
- **Branch**: iterate/generated-prefixes-provenance-anchor
- **ADR**: iterate-2026-09-12-generated-prefixes-provenance-anchor
- **Tests passed**: True
- **Spec**: Anchor or remove PR-review skip-safety per _GENERATED_PREFIXES entry, closing the gap a confirmed deploy-gate consumer (ci-security.json) exposed.

## Current Iterate Progress

- **Branch**: iterate/generated-prefixes-provenance-anchor
- **External Review Marker**: missing
- **Review Cascade**: no run_id resolved

### Mandatory replay on Resume

Before dispatching to the handoff's Remaining phase, run these if missing:
- Finalization (F0–F11) after all mandatory phases pass

## Pipeline Phases

Authoritative per-phase status from `shipwright_run_config.json` → `phase_tasks[]`; the dispatch pointer from `.shipwright/run_loop_state.json`. **A phase that merely STARTED is not finished** — only `done` / `skipped` count, so an `in_progress` row below is work to pick back up, not work banked. Phase tasks are **planned incrementally** (each one is created as its predecessor completes), so the table lists what has been planned so far, not the whole run.

- **Finished**: 5 of 7 (build, changelog, plan, project, test)
- **Interrupted**: `design` — started, not finished
- **Run status**: complete

| Phase | Split | Status | Finished? |
|-------|-------|--------|-----------|
| build | — | done | yes |
| changelog | — | done | yes |
| plan | — | done | yes |
| project | — | done | yes |
| test | — | done | yes |
| design | — | in_progress | **no — interrupted** |

## Legacy build state

- **Phase**: design
- **Current Split**: 01-adopted
- **Current Section**: adopted-baseline

- **Splits**: 0/1 complete
- **Sections**: 0/1 complete

## Git State

- **Branch**: iterate/generated-prefixes-provenance-anchor
- **Last Commit**: bf193f6a6 chore(churn): regenerate derived snapshots after main merge
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
| evt-6c5ebe28 | work_completed | iterate (Address 5 non-blocking deferred items from PR #699's review of the glossary generator's legacy CLI flag path and CONTEXT.md parser.) | 2026-09-11 |
| evt-b5e5c018 | work_completed | iterate (Record the deferred test-results-orphan retention defect (promised by trg-b28a039c, never filed) as its own triage card, with measured counts and root cause; no code fix.) | 2026-09-12 |
| evt-636423bf | work_completed | iterate (Bind FR-01.06's and FR-01.07's unbound acceptance criteria to existing/new tests via @pytest.mark.covers and regenerate the AC coverage baseline) | 2026-09-12 |
| evt-354973ae | work_completed | iterate (Raise ITERATE_RETENTION from 50 to 200 in append_iterate_entry.py, with all prose/code mirrors of the cap updated and a regression test guarding them.) | 2026-09-11 |
| evt-ca92f53b | work_completed | iterate (Fix agent_doc_budget.entry_anchor() false-anchor-match hole: an incidental bold quote elsewhere in an entry's prose could be mistaken for its cross-diff identity, letting a new over-budget entry escape the budget gate by colliding with an unrelated base entry's anchor.) | 2026-09-12 |

## Recovery

- **Pipeline**: 1 phases completed
- **Total work events**: 624
- **Last iterate**: bug — Address 5 non-blocking deferred items from PR #699's review of the glossary generator's legacy CLI flag path and CONTEXT.md parser. (2026-09-11)
- **Resume**: `/shipwright-iterate` for next change, or `/shipwright-run` for new pipeline

## Recent Decisions

### ADR-397: Tier-3 PR-review gate: DeepSeek model swap with reused ZDR routing
- **Date:** 2026-08-31
- **Section:** Iterate — change: PR-review DeepSeek model swap
- **Run-ID:** iterate-2026-08-31-pr-review-deepseek-model
- **Context:** The Tier-3 CI PR-review gate called anthropic/claude-sonnet-4.6; DeepSeek v4 Pro is cheaper/faster and the review cascade already has a fail-closed ZDR routing policy for it.
- **Decision:** Swap DEFAULT_MODEL to deepseek/deepseek-v4-pro; add pr_review_model_policy.py 
