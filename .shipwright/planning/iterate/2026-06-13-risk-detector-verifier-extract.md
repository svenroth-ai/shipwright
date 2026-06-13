# Iterate Spec — Extract risk detectors + integration-coverage verifier

- **Run ID:** `iterate-2026-06-13-risk-detector-extract`
- **Intent:** CHANGE (refactor)
- **Complexity:** medium (classifier: keyword, conf 0.70, no risk flags)
- **Spec Impact:** NONE (pure code-movement; no FR behavior change)

## Motivation

The `cross_component` gate (#218) bumped two already-oversize bloat baselines:

| File | before | after #218 | baseline state |
|---|---|---|---|
| `plugins/shipwright-iterate/scripts/lib/classify_complexity.py` | 379 | **430** | grandfathered |
| `shared/scripts/tools/verifiers/iterate_checks.py` | 1140 | **1244** | exception (ADR-093) |

The additions are load-bearing gate logic, but both files are well past the
300-LOC limit. Proportionate follow-up: relocate cohesive, already-separable
clusters into dedicated modules so both baselines ratchet back down. **No
behavior change** — code is moved verbatim and re-exported from its old home so
every existing import path keeps resolving.

## Affected Boundaries

- `shared/contracts/iterate.py` (cross-plugin public surface) — its re-exported
  names (`is_io_boundary_change`, `CROSS_COMPONENT_FILE_PATTERNS`, …) must stay
  importable. **Unchanged**: it imports from `classify_complexity`, which keeps
  re-exporting them from the new `risk_detectors` module ("internal moves stay
  internal", per the contract docstring). No `*_config.json` / `*_state.json` /
  hooks files touched → `touches_io_boundary` does NOT fire.
- The diff does **not** match `CROSS_COMPONENT_FILE_PATTERNS` — that SSoT
  deliberately excludes the gate's own meta-tooling (classify_complexity /
  iterate_checks), so `cross_component` does NOT fire on this diff (no
  integration-coverage requirement).

## Plan

### Part 1 — `risk_detectors.py` (iterate plugin lib)
New `plugins/shipwright-iterate/scripts/lib/risk_detectors.py` holds the
diff-driven detectors + pattern tables moved verbatim from `classify_complexity`:
`TOUCHES_BUILD_FILE_PATTERNS`, `touches_build_files`, `IO_BOUNDARY_FILE_PATTERNS`,
`is_io_boundary_change`, `CROSS_COMPONENT_FILE_PATTERNS`, `is_cross_component_change`.
`classify_complexity.py` re-imports them with `# noqa: F401 — re-exported
surface` (mirrors the existing `complexity_vocabulary` extraction at lines
22-25). `RISK_TAXONOMY` + message-keyword classifiers stay put.

### Part 2 — `integration_coverage.py` + `git_helpers.py` (verifiers package)
- New `shared/scripts/tools/verifiers/integration_coverage.py`:
  `_CROSS_COMPONENT_PATTERNS`, `_is_cross_component`, `_iterate_changed_paths`,
  `check_integration_coverage` (moved verbatim).
- New `shared/scripts/tools/verifiers/git_helpers.py`: the generic
  `_run_git`, `_git_available`, `_commit_changed_paths` (used by BOTH
  `iterate_checks` and `integration_coverage`; a shared home avoids a 3rd
  duplicate copy and a circular import).
- `iterate_checks.py` re-imports `check_integration_coverage` (used by
  `run_all_checks`) and re-exports `_is_cross_component` /
  `_CROSS_COMPONENT_PATTERNS` (`# noqa: F401`, pinned by the sync test); it
  imports the git helpers it still uses (`_event_committed_in_head`,
  `check_spec_impact_recorded`) from `.git_helpers`.

### Part 3 — Ratchet baselines
Update `shipwright_bloat_baseline.json` `current` for both files to the new
measured newline-count (drop the `classify_complexity` grandfather entry if it
falls ≤300). New modules are <300 LOC → no baseline entries.

## Alternative considered
Put the shared git helpers in `verifiers/common.py` — **rejected**: common.py is
grandfathered at 764, so adding to it would ratchet it UP (anti-ratchet block).
A dedicated `git_helpers.py` is a new <300 file with no entry. Self-contained
copies in `integration_coverage.py` were also rejected (would be a 3rd `_run_git`
copy alongside iterate_checks + spec_checks → bloat-detective bait).

## Confidence Calibration
- **Boundaries touched:** `shared/contracts/iterate.py` surface (unchanged,
  transitively re-exported); `tools.verifiers.iterate_checks` symbol surface
  (re-exported); `classify_complexity` symbol surface (re-exported). No IO /
  cross_component file patterns matched.
- **Empirical probes run:** (filled at F0/F0.5) import-resolution of all moved
  symbols via the package path AND via `spec_from_file_location`
  (test_record_event chain); detector/verifier/prose/sync/contract test suites;
  full lint.
- **Test Completeness Ledger:** see table below — every behavior is
  `covered-by-existing-test` (pure relocation; the safety net IS the existing
  detector/verifier/prose/sync/contract suite, which must pass UNCHANGED).
- **Confidence-pattern check:** asymptote — relocation correctness bottoms out
  at "every prior import path still resolves + every prior test green"; breadth
  — covered by re-running the full shared + iterate-plugin + integration-test
  suites, not a sampled subset. No `category:integration` behavior required
  (`cross_component` does not fire on this diff, by SSoT exclusion).

### Test Completeness Ledger
| Behavior (relocated, must stay identical) | Disposition | Evidence |
|---|---|---|
| `is_io_boundary_change` / `IO_BOUNDARY_FILE_PATTERNS` resolve from `classify_complexity` + contract | tested | `test_boundary_detection.py`, `test_shared_contracts_consumers.py` (unchanged) |
| `is_cross_component_change` / `CROSS_COMPONENT_FILE_PATTERNS` resolve via `cc.` | tested | `test_cross_component_detector.py`, `test_cross_component_patterns_sync.py` (unchanged) |
| `touches_build_files` / `TOUCHES_BUILD_FILE_PATTERNS` resolve from `classify_complexity` | tested | `test_classify_complexity_perf.py` (unchanged) |
| `classify()` output identical | tested | `test_classify_complexity.py`, `test_complexity_corpus.py` (unchanged) |
| `check_integration_coverage` behavior identical | tested | `test_check_integration_coverage.py` (unchanged) |
| `iterate_checks._CROSS_COMPONENT_PATTERNS == cc` SSoT (both directions) | tested | `test_cross_component_patterns_sync.py` (unchanged) |
| `run_all_checks` / `verify_iterate_finalization` surface intact | tested | `test_verify_iterate_finalization.py` (unchanged) |
| `mod.is_io_boundary_change` via `spec_from_file_location` | tested | `test_record_event.py::test_changed_files_round_trip_with_is_io_boundary_change` |
