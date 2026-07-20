# Iterate Spec: adopt-shared-loader-guard

- **Run ID:** iterate-2026-07-20-adopt-shared-loader-guard
- **Type:** change
- **Complexity:** medium
- **Status:** draft

## Goal
Eight adopt scaffolders each carry their own copy of a `spec_from_file_location`
loader for a `shared/scripts/lib/` helper, and all eight are unguarded: a missing
`shared/` tree surfaces as a bare `FileNotFoundError` out of `exec_module` (not a
legible `ImportError`), and two of them (`baseline_generator`,
`gitattributes_scaffolder`) additionally register the module in `sys.modules`
*before* `exec_module`, so a raising load poisons the cache (trg-a67aa561).
Extract one guarded loader helper and route the eight scaffolders through it.

## Acceptance Criteria
- [ ] A single `lib/shared_loader.load_shared_module(relative_path, sentinel)`
      helper resolves `<repo>/shared/<relative_path>`, guards with `is_file()`,
      and raises a **named `ImportError`** (never a bare `FileNotFoundError`)
      when the `shared/` tree is absent.
- [ ] The helper registers the module in `sys.modules` **only after**
      `exec_module` succeeds — a failing load never leaves a half-initialised
      module memoised under the sentinel (no cache poisoning).
- [ ] All eight unguarded scaffolders
      (`automerge_setup_scaffolder`, `baseline_generator`, `ci_workflow_scaffolder`,
      `claude_review_workflow_scaffolder`, `codeql_workflow_scaffolder`,
      `gitattributes_scaffolder`, `gitleaks_config_scaffolder`,
      `security_workflow_scaffolder`) load their shared helper via the new helper.
- [ ] Every rewired scaffolder still resolves its shared symbol on a normal
      install (full adopt suite green — no behaviour regression).

## Spec Impact
- **Classification:** none
- **ADD:** none
- **MODIFY:** none
- **REMOVE:** none
- **NONE justification:** Behaviour-preserving internal hardening of adopt's
  plugin-loading path. FR-01.13 (`/shipwright-adopt`) is unchanged on a normal
  install; only the *failure mode* when `shared/` is absent improves (legible
  `ImportError` instead of a bare `FileNotFoundError`) and a latent cache-poison
  bug is removed. No FR description or acceptance criterion changes.

## Out of Scope
- The three already-correct loaders (`adopt_brief_intake`, `spec_table`,
  `traceability_layers`) — they already guard with `is_file()`/candidate-exists
  and register after `exec_module`. `spec_table` additionally uses a
  multi-candidate path list that does not fit the single-path helper signature.
  Converging them is a separate, lower-value refactor with no bug to fix.
- The `_shipwright_planning_discovery` loader shared by `review_runner` /
  `checks/*` — a different helper with its own path-candidate logic; not part of
  the eight named in the triage.

## Design Notes
New module `plugins/shipwright-adopt/scripts/lib/shared_loader.py` mirrors the
correct reference (`adopt_brief_intake._load_brief_intake`): repo-root via
`parents[4]`, sentinel cache, `is_file()` guard → `ImportError`, spec/loader
None → `ImportError`, `exec_module` then register. Each scaffolder replaces its
inline `_load_module` / `_load_*` body with a one-line delegation carrying a
POSIX `relative_path` under `shared/` and a unique sentinel.

## Affected Boundaries
n/a — no serialized format is produced or consumed; this changes an in-process
module-import path only.

| Producer (writes) | Consumer (reads) | Format |
|---|---|---|
| n/a | n/a | n/a |

## Confidence Calibration
- **Boundaries touched:** none (module-import path only; no serialized I/O).
- **Empirical probes run:**
  - Point the helper at a non-existent `shared/` path → asserted `ImportError`
    (named), not `FileNotFoundError`.
  - Force a shared module whose `exec_module` raises → asserted the sentinel is
    absent from `sys.modules` afterward and a second call re-raises (no poison).
  - Full adopt suite (453+) after rewiring each of the eight scaffolders → the
    real load path for every rewired scaffolder still resolves its symbol.
- **Test Completeness Ledger:** mirrored into
  `iterate_latest.test_completeness` (F5): helper-guard, no-poison, cache-hit,
  and per-scaffolder still-loads behaviours are all `tested`; 0 untested-testable.
- **Confidence-pattern check:** depth — the guard/poison behaviours are pinned by
  direct unit tests with a monkeypatched repo-root, not by re-reading the diff;
  breadth — every one of the eight rewired call sites is exercised by the
  existing per-scaffolder suites. No `cross_component` machinery is touched, so
  no integration-composition behaviour is required.
