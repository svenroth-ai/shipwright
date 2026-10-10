# Iterate Spec: adopt-drop-claude-review

- **Run ID:** iterate-2026-10-10-adopt-drop-claude-review
- **Type:** change
- **Complexity:** medium
- **Status:** draft

## Goal
Adopted repos stop receiving the Claude-Code-Review workflows (`claude-review.yml` + `claude-review-run.yml`). Decision (Sven, 2026-10-10): they are ACTIVE on every PR but only know `ANTHROPIC_API_KEY`, so repos without that secret get a red/pending review on every PR; CI setup beyond the shipped security chain is individual; the independent review already runs inside each iterate (spec/code/doubt reviewers).

## Acceptance Criteria
- [ ] `generate_adoption_artifacts.py` writes no `.github/workflows/claude-review*.yml` and its result payload has no `claude_review_workflow` / `claude_review_run_workflow` key (asserted by `test_adopt_pipeline_subprocess.py`).
- [ ] `plugins/shipwright-adopt/scripts/lib/claude_review_workflow_scaffolder.py`, `shared/templates/github-actions/claude-review.yml.template` and `claude-review-run.yml.template` no longer exist, and `ci_workflow.py` carries no `CLAUDE_REVIEW_*` constant (asserted by `test_claude_review_scaffolder_is_retired`).
- [ ] `automerge_readiness.KNOWN_WORKFLOWS` is exactly `ci.yml`, `security.yml`, `codeql.yml`; `POSTED_STATUS_CONTEXTS` keeps `pr-review-run.yml` plus a documented LEGACY `claude-review-run.yml` entry (`LEGACY_POSTED_STATUS_WORKFLOWS`) so required-checks drift does not call an earlier-adopted repo's still-posted `Claude Code Review` a phantom (pinned by `test_legacy_adopted_review_context_is_not_a_phantom`); a scaffolded repo's required-check list and rendered `AUTOMERGE_SETUP.md` contain neither `claude-review` nor `Claude Code Review` and no `| active |` row.
- [ ] `ci.yml` / `security.yml` / `codeql.yml` scaffolds are unchanged (their tests pass untouched); Shipwright's own `.github/workflows/pr-review*.yml` and its fail-closed / fork-trust tests still pass (monorepo pair only).
- [ ] Docs (`step-e-artifact-generation.md` item 15, `artifact-templates.md`, adopt `SKILL.md`, `docs/guide.md`, `docs/hooks-and-pipeline.md`) describe E.15/E.15a as retired; a CHANGELOG `Removed` drop tells already-adopted repos to delete the two files manually.

## Spec Impact
- **Classification:** none
- **ADD:** none
- **MODIFY:** none
- **REMOVE:** none
- **NONE justification:** no FR in `.shipwright/planning/*/spec.md` names the adopted-repo review workflows. FR-01.17 ("Independent re-check on the code host") describes the monorepo's own gate, which is untouched (`pr-review*.yml` stays).

## Out of Scope
- Already-adopted repos: never delete user files (note in CHANGELOG only).
- `ci.yml` / `security.yml` / `codeql.yml` scaffolds (stay dormant, unchanged).
- Shipwright's own `.github/workflows/pr-review*.yml`.
- Follow-up (not filed): optional dormant OpenRouter/gateway PR review ported from `pr_review.py`.

## Design Notes
n/a (no UI).

## Affected Boundaries
| Producer (writes) | Consumer (reads) | Format |
|---|---|---|
| `generate_adoption_artifacts.py` results dict | adopt tests / `step-e` doc | JSON keys `claude_review_*` removed |
| `automerge_readiness.KNOWN_WORKFLOWS` | `AUTOMERGE_SETUP.md` render, drift test | workflow filename tuple |

## Confidence Calibration
- **Boundaries touched:** results-dict keys; KNOWN_WORKFLOWS / POSTED_STATUS_CONTEXTS.
- **Empirical probes run:** full adopt plugin suite (705 passed); shared tests filtered to automerge/ci/pr_review/codeql/adopt/template (385 passed); end-to-end subprocess adopt run asserts no claude-review file; repo-wide grep for residual references.
- **Test Completeness Ledger:**

  | # | Testable behavior | Disposition | Evidence / reason_code |
  |---|---|---|---|
  | 1 | adopt writes no claude-review*.yml, no result keys | tested | test_adopt_pipeline_subprocess PASSED |
  | 2 | scaffolder module + templates are gone | tested | test_ci_workflow_scaffold::test_claude_review_scaffolder_is_retired PASSED |
  | 3 | required-check list / AUTOMERGE doc omit review context, no active row | tested | test_automerge_readiness + test_automerge_setup_scaffold PASSED |
  | 4 | monorepo pr-review fail-closed/fork-trust invariants still hold | tested | test_pr_review_fail_closed / test_pr_review_fork_trust PASSED |
  | 5 | ci.yml scaffold + convention + registry completeness unchanged | tested | test_ci_workflow_convention, test_ci_template_registry_completeness PASSED |
- **Confidence-pattern check:** depth — grep sweep found residuals (hooks-and-pipeline line 3241) after the first pass; fixed. Breadth — every ledger row tested, 0 untested-testable.

## Verification (medium+)
- **Surface:** cli
- **Runner command:** `cd plugins/shipwright-adopt && uv run pytest tests/test_adopt_pipeline_subprocess.py -q`
- **Evidence path:** `.shipwright/runs/iterate-2026-10-10-adopt-drop-claude-review/`

## Internal Plan Review (opus-plan-reviewer)
- **Ran:** yes
- **Severity:** medium
- **Summary:** Removal complete and consistent; no live consumer of the deleted pieces; gap is the migration note for adopted repos.
- **Findings:** completeness/medium fixed (changelog + step-e now say: drop the required check first, then delete files); completeness/low fixed (absence assertion now plants a legacy claude-review.yml); completeness/low disclosed (re-render on an already-adopted repo omits the leftover check); completeness/low declined (test-traceability.json is generated, refreshed at release); architecture/low no change (POSTED_STATUS_CONTEXTS keeps pr-review-run.yml, read by deliver_pr_non_converging / required_checks_drift).
- **Known limitations:** a re-rendered AUTOMERGE_SETUP.md in an already-adopted repo does not mention a leftover claude-review*.yml.
- **Status:** 2 fixed, 1 disclosed, 1 declined

## Internal Architecture Review (architecture-internal-reviewer)
- **Ran:** yes
- **Severity:** low
- **Summary:** Removal justified and smallest option; only gap is the migration ordering.
- **Findings:** completeness/medium fixed (same migration-note fix); necessity, smallest-option, security, complexity-cost low, no action.
- **Known limitations:** none
- **Status:** 1 fixed

## Architecture Review
- **Brief:** `.shipwright/planning/iterate/iterate-2026-10-10-adopt-drop-claude-review/architecture_brief.md`
- **Verdicts:** glm=revise · openai=revise
- **Smallest thing that would do (per reviewers):** as proposed
- **Findings:** both: migration note must tell adopters to remove the required check from branch protection (accepted-and-fixed); glm: unknown-workflow drift noise for leftover files (checked: KNOWN_WORKFLOWS only scopes the AUTOMERGE doc, no drift failure — accepted-with-reason), exact-match of posted contexts (pinned by existing dict lookup)
- **Reconciliation:** the plan's rejected alternative (dormant workflows) was not re-proposed; both reviewers agree pure removal is right.

## Doubt Review (doubt-reviewer)
- **Doubt 1 (medium) — fixed:** dropping the `claude-review-run.yml` POSTED_STATUS_CONTEXTS entry would make `required_checks_drift` (run in every adopted repo) report a kept review's context as phantom. Entry restored as LEGACY, with a drift test. The earlier Architecture Review rebuttal ("KNOWN_WORKFLOWS only scopes the AUTOMERGE doc") was incomplete and is superseded by this.
- **Doubt 2 (medium) — fixed:** the template deletions match `touches_ci_supplychain` (`shared/templates/github-actions/**`); a `ci_supplychain_ack.json` is recorded for this run and risk flag noted.
