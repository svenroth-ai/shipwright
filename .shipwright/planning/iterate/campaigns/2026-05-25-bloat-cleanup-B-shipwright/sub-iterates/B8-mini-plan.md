# B8 Mini-Plan — shared/contracts/* + adopt-bridge + test-boundary refactor

## Goal

Introduce the first cross-plugin contracts in `shared/contracts/`,
eliminating the two subprocess/path-walk patterns the adopt-bridge and
the test plugin's boundary-coverage-report currently use to consume the
compliance and iterate plugins respectively.

## Changes

1. **NEW** `shared/contracts/__init__.py` (29 LOC) — package shim that
   re-exports `compliance` and `iterate` submodules for the convenience
   form `from shared.contracts import compliance`.

2. **NEW** `shared/contracts/compliance.py` (117 LOC) — typed re-export
   facade over `plugins/shipwright-compliance/scripts/lib/data_collector.py`.
   Exposes `collect_all`, `ComplianceData`, and the supporting dataclasses
   (`WorkEvent`, `TestRunEvent`, `SplitInfo`, `SectionInfo`, `TestResults`,
   `DecisionEntry`, `CommitEntry`, `DependencyInfo`, `RequirementInfo`,
   `KnownFailure`, `ExternalReviewState`). Bootstraps the compliance
   plugin root onto `sys.path` ONCE at module load, anchored on the
   contract file's own location — no ancestor-walk.

3. **NEW** `shared/contracts/iterate.py` (108 LOC) — typed re-export
   facade over `plugins/shipwright-iterate/scripts/lib/classify_complexity.py`.
   Exposes `is_io_boundary_change`, `touches_build_files`, `classify`,
   `RISK_TAXONOMY`, `IO_BOUNDARY_FILE_PATTERNS`,
   `TOUCHES_BUILD_FILE_PATTERNS`, `COMPLEXITY_ORDER`. Same bootstrap
   pattern as the compliance contract.

4. **REFACTOR** `plugins/shipwright-adopt/scripts/lib/compliance_bridge.py`
   (116 → 214 LOC).
   - Removed: `subprocess.run` invocation of `update_compliance.py`,
     `_compliance_script` ancestor-walk, two `sys.path.insert` calls in
     `run_lib_fallback`.
   - Added: in-process generator dispatch via `_PHASE_REPORTS` (mirrors
     `update_compliance.PHASE_REPORTS`) + `_REPORT_TO_GENERATOR` (module
     name → output-file mapping) + `_import_generator` helper that uses
     `importlib.import_module` with a static nosemgrep comment.
   - Public surface unchanged: `run_update_compliance(project_root, phases)`
     and `run_lib_fallback(project_root)` both keep their signatures and
     return-dict shapes.

5. **REFACTOR** `plugins/shipwright-test/scripts/tools/boundary_coverage_report.py`
   (661 → 640 LOC).
   - Removed: `_REPO_ROOT_GUESS`, `_ITERATE_LIB` constants, `sys.path.insert`,
     `try/except` fallback import + inline `is_io_boundary_change`
     duplicate function.
   - Added: single `from shared.contracts.iterate import is_io_boundary_change`
     line.

6. **EDIT** `plugins/shipwright-adopt/scripts/tools/seed_adopt_compliance.py`
   — `_load_lib()` now also adds the repo root to `sys.path[0]` so the
   bridge's `from shared.contracts.compliance import collect_all` resolves
   when the tool is invoked from the adopt plugin's own `.venv`.

7. **EDIT** `plugins/shipwright-test/tests/conftest.py` — adds repo root
   to `sys.path` for the same reason as item 6 (the test plugin's
   `.venv` does not ship the monorepo's namespace packages).

8. **NEW** `integration-tests/test_shared_contracts_consumers.py`
   (231 LOC, 20 tests) — round-trip probe + static-source guards:
   - Both contracts importable at module scope.
   - `collect_all` returns a `ComplianceData` instance against a minimal
     fixture project root.
   - `is_io_boundary_change` parametrized over 10 positive/negative cases.
   - Static-source assertions on `compliance_bridge.py` (no
     `subprocess.run/Popen`, no `*here.parents` walk, no
     `sys.path.insert`).
   - Static-source assertions on `boundary_coverage_report.py` (no
     `_ITERATE_LIB`, no `sys.path.insert`).

## Verification

- Integration test suite: 20/20 pass (new) + 130/130 pre-existing pass.
- `plugins/shipwright-adopt/tests/` — 297/297 pass.
- `plugins/shipwright-test/tests/` — 143/143 pass.
- `plugins/shipwright-compliance/tests/` — 528/528 pass.

## Risks + Mitigations

- **Backwards compatibility.** Contract pins the symbol names that
  downstream consumers rely on. Future iterates (B2 splits compliance
  data_collector; B6 splits github_triage; etc.) MUST keep the same
  names importable from `scripts.lib` so the contract's re-exports
  remain valid. The integration test pins which names are part of the
  surface; any breaking change there fails the integration suite.

- **PHASE_REPORTS drift.** `compliance_bridge._PHASE_REPORTS` duplicates
  `update_compliance.PHASE_REPORTS`. If the compliance plugin adds a new
  phase, the bridge must mirror it. Acceptable trade-off: avoids a
  cross-plugin import for a 12-entry table that changes once per quarter.

- **Plugin-venv shared bootstrap.** Two callers (`seed_adopt_compliance.py`
  and `plugins/shipwright-test/tests/conftest.py`) had to add the
  repo root to `sys.path` because their venvs do not ship the
  monorepo's top-level `shared/` namespace package. Both bootstraps are
  TIGHTLY anchored (no walk) and live at the EDGE (callers of the
  contract), not in the contract itself.
