# Mini-plan: BL0b broader measurement before BP goes further

Spec: campaign baseline-protection, sub-iterate BL0b (`.shipwright/planning/iterate/campaigns/baseline-protection/sub-iterates/BL0b-broader-measurement.md`); brief sections 0-2 and 8.

## Work
1. Setup: `bl0b_head_run.py` runs every pytest root serially as CI does (plugin roots from the plugin directory), contexts on, one database per root, root-prefixed at load.
2. HEAD context run mapped to history by qualified name (`_baseline_b_headmap.py`); cross-check against the stored merge-base results.
3. Path-ownership baseline (`_baseline_b_paths.py`); new-code classes a/b; AC-level tokens.
4. 50 blind mutation probes judged by a failing FR-bound test (`_baseline_b_probes.py`, `bl0b_probes.py`).
5. 35 blind label packs (`_baseline_b_packs.py`) -> two independent labelers -> `_baseline_b_eval.py` evaluates the pre-registered rules unchanged.
6. Report `.shipwright/planning/campaigns/2026-10-27-baseline-protection-BL0B.md` and `.json`.

## Tests
L1 tests on real git for mapping, new-code class, path baseline, mutation and pack redaction (`test_baseline_b.py`).

## Risks
Measurement only; nothing gates. The long runs are serial and time-boxed; cuts are disclosed in the report.
