# Iterate Spec: codeql-action-v4-bump

- **Run ID:** iterate-2026-08-05-codeql-action-v4-bump
- **Type:** change
- **Complexity:** medium
- **Status:** draft

## Goal
Bump `github/codeql-action` from `@v3` to `@v4` in this repo's own CodeQL
workflow and in the shipwright-adopt scaffolding template it ships to every
adopted/new project, closing the one remaining v3 pin (GitHub deprecates
CodeQL Action v3 in December 2026 and removes Node.js 20 runner support in
fall 2026; `security.yml`'s `upload-sarif` step was already migrated to v4
on 2026-05-11).

## Acceptance Criteria
- [ ] AC1: `.github/workflows/codeql.yml`'s three `github/codeql-action/*`
      steps (`init`, `autobuild`, `analyze`) read `@v4`.
- [ ] AC2: `shared/templates/github-actions/codeql.yml.template`'s three
      `github/codeql-action/*` steps (`init`, `autobuild`, `analyze`) read
      `@v4`.
- [ ] AC3: `permissions`, `continue-on-error`, `queries:`, and `config-file:`
      on the analyze/init steps are byte-identical to before the bump — only
      the version pins change.
- [ ] AC4: `shared/tests/test_codeql_workflow_convention.py` and
      `shared/tests/test_codeql_config_query_filters.py` gain an explicit
      assertion that fails on `@v3` and passes on `@v4`, so the pin cannot
      silently regress.

## Spec Impact
- **Classification:** none
- **NONE justification:** behavior-preserving CI dependency version bump
  (third-party GitHub Action major-version pin). No FR describes CI Action
  version pins; no user-visible product behavior changes. `change_type:
  infra`.

## Out of Scope
- `security.yml`'s `upload-sarif` step — already on `@v4` since 2026-05-11.
- Query suite, `continue-on-error`, or permissions changes.
- The separate `shipwright-webui` repository — same fix, but its own
  worktree/PR since it is a different git repository (tracked as a
  follow-up in this session, not part of this iterate's commit).

## Design Notes
n/a — no UI, no design surface touched.

## Affected Boundaries
n/a — a GitHub Action version pin is not a serialized producer/consumer
format; no boundary crossing changes.

## Confidence Calibration
- **Boundaries touched:** none
- **Empirical probes run:** confirmed via GitHub's own changelog
  (github.blog/changelog, 2025-09-19 and 2025-10-28 posts) that v4 is GA,
  Node-24-based, and the documented replacement for v3; read back the exact
  diff hunks in both files to confirm only the version token changed.
- **Test Completeness Ledger:**

  | # | Testable behavior | Disposition | Evidence / reason_code |
  |---|---|---|---|
  | 1 | `codeql.yml` init/autobuild/analyze pin `@v4` | tested | `test_codeql_config_query_filters.py::test_codeql_action_steps_pin_v4` PASSED |
  | 2 | `codeql.yml.template` init/autobuild/analyze pin `@v4` | tested | `test_codeql_workflow_convention.py::test_codeql_action_steps_pin_v4` PASSED |
  | 3 | permissions / continue-on-error / queries / config-file unchanged | tested | existing `test_explicit_permissions_floor`, `test_analyze_step_continue_on_error`, `test_workflow_references_config_file`, `test_workflow_keeps_security_and_quality_suite` all still PASSED after the edit |
  | 4 | rendered template (placeholder substituted) stays valid YAML | tested | existing `test_rendered_template_is_valid_yaml` PASSED |

- **Confidence-pattern check:** asymptote — no prior "are you confident?"
  probe in this run to re-check. Coverage — all 4 ledger rows `tested`, 0
  untested-testable.

## Verification (medium+)
- **Surface:** none
- **Runner command:** n/a
- **Evidence path:** n/a
- **Justification (only if surface=none):** pure CI-workflow-file version-pin
  change with no client/server runtime surface; verified via the pytest
  meta-tests listed in the Test Completeness Ledger instead of a live
  surface run.
