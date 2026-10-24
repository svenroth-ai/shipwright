# Mini-plan A3: validator fixes (campaign brief-driven-run-a-real-gates)

Goal: make the phase validators correct before A4 wires them into the driven (v2) apply path. Brief F18b, D4 step (1), acceptance A3.

Problem: `_validate_design` looks for mockups per project-config split under `.shipwright/planning/<split>/mockups/` while the design skill writes project-global screens to `.shipwright/designs/screens/`; it reads splits from the project config while `freeze_splits` prefers the design config; with no splits it passes vacuously; a non-UI run gets "No mockups found". `_validate_plan` reads `build_config.current_split` instead of the task's split. Test layers accept `skip_reason` only for integration (smoke/e2e need `reason`). `_run_canon_checks` swallows `ImportError` and reads the run id only from the environment, so a skipped canon gate and an unchecked `phase_history` both look like a clean pass.

Changes:
1. New `phase_validators_split.py` holds `_validate_design` and `_validate_plan` (moved out of `phase_validators.py`, which shrinks 228 -> 165, net-negative). Split membership via `phase_task_planning._resolve_splits_with_fallback` (the freeze_splits authority: design config, then project config).
2. Design: pass on any `.shipwright/designs/screens/*.html`; else legacy per-split mockups required for every split (or the given `split_id`); no screens and no splits -> ask. Not applicable (pass + inform): run_config `scope=library` (mirrors design_checks `_NO_UI_SCOPES`, pinned by test) or the run's design phase task `skipped` in `phase_tasks[]` (revised after the internal architecture review: a skip recorded in the design config is self-certified by the gated phase and is not trusted).
3. Plan: uses `split_id` when given; when build config's `current_split` is set and differs, ask (sections on record belong to another split); without split_id falls back to `current_split` (unchanged).
4. `validate_phase(step, root, *, split_id=None, run_id=None)`; every validator takes the two keywords; canon bridge takes `run_id` (None -> env fallback). A4 passes `config.runId` and the task split from `run_phase_gate`.
5. Canon bridge: ImportError -> inform note `[canon-degraded]` with `kind: canon_degraded`; empty run id -> same kind of note ("phase_history not checked"). Inform, not ask: the phase's own checks still ran.
6. Test layers: `_skip_reason()` accepts `reason` or `skip_reason` for integration, smoke and e2e.
7. Docs: hooks-and-pipeline Phase Validators table + split module pointer.

Alternative approach considered: make the degraded canon an ask-level issue - rejected because environments without shared/scripts on the path (legacy stubs) would wedge every run; A4/A5 decide enforcement.

Tests: new `plugins/shipwright-run/tests/test_phase_validators_split.py` (22 cases), one late test updated for the new bridge keyword. Run plugin suite, shared verifier tests, integration run e2e.
Risks: v1 `update_step` now records a `[canon-degraded]` inform note when SHIPWRIGHT_RUN_ID is unset (visible by design); design with no splits and no screens now asks instead of passing.
