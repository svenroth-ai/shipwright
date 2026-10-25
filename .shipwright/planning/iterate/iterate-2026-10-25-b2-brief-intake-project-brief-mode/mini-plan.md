# Mini-plan: B2 brief intake from a package directory and Project brief mode

Spec: campaign brief-driven-run-b-intake-design-e2e, sub-iterate B2; BRIEF D1-D3, D10; operator decision 2026-10-25 (no extraction).

## Changes
1. shared/scripts/lib/brief_dir_intake.py (new): resolve_dir, check_approval, open_package (verify_package + approval + recorded-hash rules), intake_dir (brief fields override derived values), record / verify_run_config (brief_dir + brief_package in shipwright_run_config.json), CLI verify/record (exit 3 = refused). Loads brief_package/brief_intake as a privately named package (ADR-045), never `lib`.
2. shared/scripts/lib/brief_intake.py: routing hook only (directory or trailing slash -> sibling module via file-path loader), `intake(source, project_root=".")`, loud exit 3 in main; net -6 lines (290).
3. shared/scripts/tools/brief_project_mode.py (new): apply (verify, content checks, then write transcript pointer, requirements.md, grill-traces, CONTEXT.md terms), verify-traces (anchors resolve to non-empty sections), check-fr-names.
4. plugins/shipwright-project/scripts/write_run_config.py: --brief-dir (verify first, exit 5; brief profile wins; record).
5. Docs: run SKILL.md (Step 1/4/resume), brief-intake.md, project SKILL.md + step-8-completion.md (stale "update-step enforces" prose fixed), new references/brief-mode.md, step-1, first-actions, hooks-and-pipeline.md.
6. Tests: shared/tests/test_brief_dir_intake.py, test_brief_project_mode.py (+ helper), plugins/shipwright-project/tests/test_write_run_config_brief.py.

## Tests
One pytest root per process: shared/tests, plugins/shipwright-project, plugins/shipwright-adopt (unchanged adopt tests), ruff 0.15.15, verify_local.py.

## Alternative approach considered
Extracting brief_intake first (BRIEF B0): rejected by both architecture reviewers and the operator; the routing hook keeps adopt and the file route untouched.
