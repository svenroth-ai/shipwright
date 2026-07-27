# Mini-Plan: the review gate stops being bypassable

Run ID: `iterate-2026-07-27-review-gate-failclosed-fork` · Complexity: medium
Card: `trg-c7e5835b` items (1) + (2), PR A of two · Implements FR-01.17 (E)2,3,4,5,7

## Chosen approach

Split the review into two workflows and move the required `PR Review` context
off a job and onto a **commit status posted by stage 2**.

- **Stage 1** (`pull_request`) runs on every PR *including forks*, holds no
  credentials, decides the tier, and uploads the diff as an artifact.
- **Stage 2** (`workflow_run`, fires when stage 1 finishes) runs in the base
  repo with credentials, checks out only the base repo, reads the artifact as
  data, reviews, and posts the verdict as a comment plus the status.

## Why this shape and not the two obvious alternatives

The decisive fact: **GitHub scores a skipped job as a *successful* required
check.** So the old fork guard did not merely disable the review — it actively
turned the gate green.

| Alternative | Why rejected |
|---|---|
| Keep the `review` job as the check; add a fork-only stage 2 posting a status of the same name | The skipped job still emits a `skipped` check run under that name, so the hole stays open — and two producers of one context is the ambiguity GitHub's docs warn against. |
| Leave forks red; a maintainer clears them with `skip-pr-review` | Forks would be *blocked*, not *reviewed* — weaker than asked, and (E)7 argues against widening that label's reach. Kept as the documented fallback. |

Chosen shape is fail-closed **by construction**: no stage-2 report → context
absent → `pending` → merge blocked. That is (E)2's "silence counts as not
passing" implemented as a mechanism rather than a convention.

## Files

| # | File | Change |
|---|---|---|
| 1 | `.github/workflows/pr-review.yml` | Becomes stage 1: fork guard dropped, `PR Review` job name dropped, artifact upload added, waiver qualified by sensitive paths |
| 2 | `.github/workflows/pr-review-run.yml` | **New** — stage 2 |
| 3 | `shared/templates/github-actions/claude-review.yml.template` | Same split, shipped side |
| 4 | `shared/templates/github-actions/claude-review-run.yml.template` | **New** — shipped stage 2, fails closed on size / crash / unparseable output |
| 5 | `plugins/shipwright-security/scripts/tools/pr_review.py` | `--diff-file` so the review is pinned to the SHA stage 1 saw |
| 6 | `shared/scripts/lib/ci_workflow.py` | Register the stage-2 template + deployed path |
| 7 | `plugins/shipwright-adopt/scripts/lib/claude_review_workflow_scaffolder.py` + `generate_adoption_artifacts.py` | Scaffold both stages |
| 8 | `shared/scripts/lib/automerge_readiness.py` | `POSTED_STATUS_CONTEXTS` — stage 2 contributes a posted status, not job names, and is not dormant |
| 9 | `shared/tests/test_pr_review_fail_closed.py` | **New** — `@FR-01.17` invariants, parametrised over monorepo *and* template |
| 10 | Existing tests + `docs/hooks-and-pipeline.md` + `AUTOMERGE_SETUP.md.template` | Follow the new shape |

## Sequence (TDD)

1. **Red** — write the invariants as tests against parsed YAML. ✅ 23 failing.
2. **Green** — files 1–8. ✅
3. Update the tests that pinned the old shape — including
   `test_fork_pr_guard_present`, which *required the hole to exist*. ✅
4. Boundary round-trip on the artifact seam; docs; `ci_supplychain_ack`.

## Landing

Needs a **one-time admin merge**: stage 2 only fires from the default branch, so
it cannot report on the PR introducing it. Ruleset grants admin
`bypass_mode: always`. Every later PR is normal. Confirmed with the operator.

## Rollback

Reverting the commit restores the prior gate exactly. Both new workflows are
additive files; no state migration, nothing persisted outside the repo.
