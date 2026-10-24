# Mini-plan A2: extraction for headroom (behaviour unchanged)

Goal: free LOC headroom in four hot files that later campaign units (A3 validators, A4 override hook/gate seam, B3a design gates, B5 catalog) must edit, without changing any behaviour.

Changes (pure moves; function bodies byte-identical except import wiring):
1. shared/scripts/lib/gate_policy.py (301 -> 235): render_catalog_markdown body + ASCII/cell helpers move to new gate_catalog_render.py as render_catalog_doc(cat, *, policies_order, covered_phases, auto_default). gate_policy keeps a thin render_catalog_markdown(catalog=None) wrapper that loads the catalog and passes its own constants (renderer cannot import gate_policy: cycle). Public name and signature unchanged.
2. plugins/shipwright-run/scripts/lib/phase_validators.py (495 -> 228): _run_canon_checks -> phase_validators_canon.py; _validate_test/_changelog/_deploy/_compliance -> phase_validators_late.py. phase_validators re-imports all, _VALIDATORS unchanged. Own lib dir appended to sys.path (file is also loaded by path in a test).
3. plugins/shipwright-run/scripts/lib/phase_task_lifecycle.py (725 -> 258): leaf phase_task_core.py (lock, read/write helpers, _ok/_fail, guard, owner/version CAS check, constants), phase_task_lookup.py (get/find/validate_prerequisites), phase_task_planning.py (freeze_splits, plan_next_phase, _plan_next_inplace), phase_task_recovery.py (recover_phase_task). Lifecycle re-exports every prior name; claim/mark_failed/complete remain. DAG: core <- lookup/planning/recovery <- lifecycle.
4. shared/scripts/lib/design_gate_extras.py (300 -> 165): GateResult -> design_gate_result.py; #5/#6 -> design_gate_html.py; #9 -> design_gate_feedback.py; re-exported (dual relative/top-level import pattern kept).
5. shipwright_bloat_baseline.json: remove the 3 entries that are now under 300 (downward only). docs/hooks-and-pipeline.md: two pointer sentences.

Verification: run-plugin tests (580), shared/tests subset, design plugin tests, integration single_session tests, ruff, verify_local.
Risks: monkeypatch of moved module attrs (checked: only class-object patch of _PhaseTasksLock.__init__ and design_gate_extras.subprocess, both still valid); sibling bare-name imports (lib dir on sys.path via lifecycle/phase_validators).
