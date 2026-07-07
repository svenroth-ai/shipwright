---
canon_generated: true
run_id: "iterate-2026-07-07-gh-tag-helper-wire-in"
phase: "iterate"
reason: "iterate: wire GH-owned action-tag call-sites through the shared predicate"
timestamp: "2026-07-07T08:35:35.699695+00:00"
---

# Session Handoff

> Auto-generated 2026-07-07 08:35:35 UTC

## Session Info

- **Session ID**: 5f961e7b-133b-440e-b3b1-0a699abb66cb
- **Timestamp**: 2026-07-07 08:35:35 UTC
- **Reason**: iterate: wire GH-owned action-tag call-sites through the shared predicate

## Last Iterate

- **Run ID**: iterate-2026-07-06-semgrep-accept-producer
- **Date**: 2026-07-06T22:35:44.589840Z
- **Type**: bug
- **Complexity**: small
- **Branch**: iterate/semgrep-accept-producer
- **ADR**: iterate-2026-07-06-semgrep-accept-producer
- **Tests passed**: True

## Current Iterate Progress

- **Branch**: iterate/gh-tag-helper-wire-in
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

- **Branch**: iterate/gh-tag-helper-wire-in
- **Last Commit**: ab114c8c fix(security): drop accepted-risk GH-owned action-tags at the SARIF artifact producer (#336)
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
| evt-fe2d0f53 | work_completed | iterate (Behavior-preserving simplify: route both GH-owned action-tag call-sites (security_findings._is_accepted_gh_owned_tag + plugin semgrep_tailoring._is_github_owned_action_tag) through the single shared gh_action_tag_owner.is_github_owned_action_tag predicate; drop the now-unused primitive imports. Follow-up to iterate-2026-07-06-semgrep-accept-producer which shipped that helper unused.) | 2026-07-07 |
| evt-2bcbc1b9 | work_completed | iterate (Diff-coverage adopt-template rollout: add a warn-only diff-coverage job to the two vitest CI templates (ci-supabase-nextjs flat + ci-vite-hono client/server) so every future adopted vitest repo gets a changed-line coverage gate (npm cobertura -> pinned uvx diff-cover@10.3.0 --fail-under=80, continue-on-error, ubuntu-only, PR-gated, dormant). diff-cover resolves each package's paths natively via cobertura <source> (no combine). Proven end-to-end on WebUI PR #205.) | 2026-07-06 |
| evt-aebeb6f0 | work_completed | iterate (Lift the owner-scoped GH-owned-action-tag Semgrep tailoring predicate into a shared util and apply the opt-in drop at the SARIF artifact-ingest path (security_findings._findings_from_sarif) so the gh-security triage producer and Control-Grade Security dimension stop over-counting accepted-risk GH-owned mutable-action-tags for adopted repos; third-party stays flagged.) | 2026-07-06 |
| evt-b56b6097 | work_completed | iterate (Compliance dashboard honesty: rewrite the _diff_coverage_block.py wording so diff-coverage reads as a graded Control-Grade Test-Health input (target >=80%), not '(informational, not yet graded)'. Both prior claims became false after Phase 3 (graded) + the Phase-7 hard flip (enforced CI gate). Kept generic (no hardcoded 'blocks merge') since the renderer is repo-agnostic and lights up on any managed repo that produces the transient.) | 2026-07-06 |
| evt-0e47577b | work_completed | iterate (Cold-repo Control Grade caps at B (A is authoritative-only): the projector declares change_reconciliation the one expected_dimensions entry so the honesty gate caps a cold headline at B. Heuristic-only; dogfood stays A.) | 2026-07-06 |

## Recovery

- **Pipeline**: 1 phases completed
- **Total work events**: 270
- **Last iterate**: change — Behavior-preserving simplify: route both GH-owned action-tag call-sites (security_findings._is_accepted_gh_owned_tag + plugin semgrep_tailoring._is_github_owned_action_tag) through the single shared gh_action_tag_owner.is_github_owned_action_tag predicate; drop the now-unused primitive imports. Follow-up to iterate-2026-07-06-semgrep-accept-producer which shipped that helper unused. (2026-07-07)
- **Resume**: `/shipwright-iterate` for next change, or `/shipwright-run` for new pipeline

## Recent Decisions

### ADR-235: Dedup the bloat-gate Stop block across the plugin fan-out
- **Date:** 2026-06-20
- **Section:** shared/scripts/hooks/bloat_gate_on_stop.py
- **Run-ID:** iterate-2026-06-20-bloat-gate-stop-fanout-dedup
- **Context:** The bloat gate is registered in all 12 plugins, so one Stop event fires it 12x. PR #250 (hook-fanout-dedup) guarded audit/handoff/drift but listed bloat_gate_on_stop as 'already convergent' — wrong: its empty pass path is invisible, masking that the BLOCK path re-emits the full 
