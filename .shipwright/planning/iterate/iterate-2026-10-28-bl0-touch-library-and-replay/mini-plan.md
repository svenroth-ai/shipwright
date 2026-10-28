# Mini-plan: BL0 touched-set library and replay

Spec: campaign baseline-protection, sub-iterate BL0 (brief `.shipwright/planning/campaigns/2026-10-27-baseline-protection-BRIEF.md` sections 0-2, 3 (BL0), 4, 6, 8).

## Work
1. Library `shared/scripts/tools/verifiers/_baseline_touch_{git,spec,binding,static,coverage,core,replay_stats,replay_code}.py`: git diff reader (3-way read), T-spec (normative digest per FR, markers/order ignored), T-test (qualified-name index, body+decorator+mark digest, covers bindings incl. module/class marks, moved = same digest+bindings), static test-dir attribution (fixture/conftest/helper), T-code from per-test coverage contexts (base-run; enclosing-function attribution; fan-out), scope rule (`evaluate_hold`: touched & existing - (scope|moved|broad), fail-closed on incomplete).
2. `shared/scripts/tools/replay_baseline_lock.py`: last 100 merged PRs (gh), squash first-parent as merge base, historical `fr_impact` -> `affected_frs` -> none, PR class, hold rate, sample; `--code-sample 20` runs context runs at merge bases; `--probes` seeds mutations.
3. L1 tests (real git, real coverage DB): `test_baseline_touch.py`, `test_baseline_touch_coverage.py`, seeded S1-S5, S6, S7, S8, S17 equivalents.
4. REPLAY report `.shipwright/planning/campaigns/2026-10-27-baseline-protection-REPLAY.md` with every stop-1 input.

## Tests
L1 as above; replay is reproducible from its JSON (`--from-json`).

## Risks
Context runs at 20 merge bases are expensive: a restricted tier set is used and disclosed. Heuristic labels in the report are provisional; the operator re-labels a random sample.
