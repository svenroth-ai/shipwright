# Mini-Plan: adopt-drop-claude-review

- **Run ID:** iterate-2026-10-10-adopt-drop-claude-review

## Files
- delete: `plugins/shipwright-adopt/scripts/lib/claude_review_workflow_scaffolder.py`, `shared/templates/github-actions/claude-review.yml.template`, `claude-review-run.yml.template`
- edit: `generate_adoption_artifacts.py` (drop E.15 call), `shared/scripts/lib/ci_workflow.py` (drop `CLAUDE_REVIEW_*`), `automerge_readiness.py` (KNOWN_WORKFLOWS, POSTED_STATUS_CONTEXTS), `AUTOMERGE_SETUP.md.template` (drop review paragraph), docstrings in codeql/helper/automerge scaffolders
- docs: step-e item 15 -> retired, artifact-templates, adopt SKILL.md, guide, hooks-and-pipeline
- tests: test_ci_workflow_scaffold, test_automerge_setup_scaffold, test_adopt_pipeline_subprocess, test_shared_loader, test_codeql_workflow_scaffold, shared: test_automerge_readiness, test_ci_workflow_convention, test_ci_template_registry_completeness, _pr_review_workflows, test_pr_review_fail_closed, test_pr_review_fork_trust
- changelog drop (Removed)

## Work breakdown
1. Remove scaffolder + templates + constants; unhook call site.
2. Shrink KNOWN_WORKFLOWS / POSTED_STATUS_CONTEXTS; drop doc paragraph.
3. Update tests (retire review-specific ones; assert absence).
4. Docs + changelog.
5. Verify: ruff, adopt suite, shared filtered suite, full F0.

## Test strategy
Absence assertions in the e2e adopt subprocess test and the retired-module test; automerge doc asserts no review context and no active rows.

## Alternative approach
Keep the scaffolder but write the workflows dormant (`workflow_dispatch` only) — rejected: still ships a template needing a secret nobody asked for, and the Required-Check list would still have to special-case it. The decision is to not ship it at all.
