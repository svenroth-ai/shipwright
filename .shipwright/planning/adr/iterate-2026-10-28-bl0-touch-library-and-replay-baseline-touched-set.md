# Baseline touched-set: measure first, as a library plus a replay

Unit BL0 of campaign `baseline-protection`. The binding source is `.shipwright/planning/campaigns/2026-10-27-baseline-protection-BRIEF.md`; the measured result is `.shipwright/planning/campaigns/2026-10-27-baseline-protection-REPLAY.md`.

## Decision

Build the touched-set derivation (T-spec, T-test, moved, static test-dir attribution, T-code from per-test coverage contexts, the scope rule) as `verifiers/_baseline_touch_*.py`, and a manual replay CLI `tools/replay_baseline_lock.py`; run the replay over the last 100 merged PRs, T-code over 20, plus mutation probes; stop for the operator. Nothing gates and nothing runs in CI.

Disclosed deviations (also in the REPLAY report, section 12): T-spec uses a purpose-built reader instead of keystone's AC digest (keystone keys criteria by AC id and ignores the statement, the brief's ignore list says the opposite); manifest runtime-id bindings are deferred (function-level static bindings over-approximate); `_baseline_touch_static.py` and `_baseline_touch_coverage.py` are replay-grade prototypes that BL2 owns.

## Architecture Review

Architecture brief: three options (build the library and replay; extend the existing gates with a report; do nothing). Internal `architecture-internal-reviewer` (opus): approve, with notes to pin the PR set by SHA, put the stop-1 input list in the spec and say what happens to the library if stop 1 rejects the gate. External GLM and OpenAI: both approve; both advise reusing the existing keystone / test-digest derivations where practical (taken only where it could be done without breaking the brief's ignore list; see the deviation above). The replay JSON pins the 100 PRs by merge SHA.

## Internal Plan Review (opus-plan-reviewer)

High: stop-1 checklist and labels per source (done in the REPLAY report, section 1 and 8); fail-open in `line_changes` and missing contexts (fixed: raises / `require_code`). Medium: two-dot diff (fixed: merge-base); static/coverage are BL2's (labelled prototypes); biased tier selection (fixed: PRs chosen inside measured targets); shared venv timing; diff coverage (in-process tests added); reproducibility (JSON snapshot committed next to the report). Low: probe docstring, env scrubbing and workdir guard (fixed), git output parsing.

## External-Plan-Review-Findings

| Finding | Severity | Disposition |
|---|---|---|
| Too many modules before they earn their split | medium | rejected-with-reason: replay-only modules are separable on purpose so they can be deleted if stop 1 stops BP |
| T-spec normalization under-specified | medium | accepted-and-fixed: rules in the module docstring, tests for reformat vs real edit |
| Squash first-parent assumption | high | accepted-and-fixed: all 100 PRs were squash commits (REPLAY section 12), merge base resolved with `git merge-base` |
| Overlap check against open units | high | accepted-and-fixed: the e2e-run-findings brief on main names none of this unit's files |
| Restricted tiers make T-code incomplete | medium | accepted-and-fixed: PR selection inside measured targets, split reported, N conditional |

## Code review

Stage 1 spec review: round 1 REJECT (4 divergences), round 2 PASS. Stage 2 code review: round 1 two highs (fixture chains, class members) fixed; round 2 one high (module-level statements) fixed with tests but the round cap was reached, so `code` and `doubt` are recorded `not_run` / `delegated-to-orchestrator` for 3f-bis.

## External-Code-Review-Findings

| Finding | Severity | Disposition |
|---|---|---|
| No committed REPLAY report in the diff | high | accepted-and-fixed: the report and JSON are committed under `.shipwright/planning/campaigns/` (outside the reviewed `shared/` diff) |
| Added `conftest.py` skipped by static attribution | high | accepted-and-fixed: an added conftest is processed; test added |
| Manifest runtime bindings deferred | high | rejected-with-reason: function-level bindings over-approximate; deferral disclosed, left to BL2/BL3 |
| `gh pr list` not ordered by merge time | medium | rejected-with-reason: the replay pins the selected PRs and merge SHAs in the JSON; recency order is by number |
| `select_prs(records, 0)` returns all | medium | accepted-and-fixed |
| Moved + re-tagged test missed | medium | accepted-and-fixed: both bindings are hit; test added |

## Consequences

The operator decides at stop 1 from measured numbers: 39 of 100 PRs would be held with an empty scope (27 of them friction, 12 undeclared), T-code saw a hit in 2 of 20 sampled PRs, a seeded change to FR-bound code is noticed and a prose change is not.
