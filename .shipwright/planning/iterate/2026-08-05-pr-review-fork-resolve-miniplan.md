# Mini-Plan: fork PRs still fail Tier-3 PR review — resolver endpoint

- **Run ID:** iterate-2026-08-05-pr-review-fork-resolve

## Files to modify

- `.github/workflows/pr-review-run.yml` — edit: swap the resolve step's `gh
  api` source query + jq filter.
- `shared/templates/github-actions/claude-review-run.yml.template` — edit:
  same swap, kept in parity with the monorepo's own file per the existing
  `_pr_review_workflows.py` `STAGE1_STAGE2` pairing.
- `shared/tests/test_pr_review_fork_trust.py` — edit: add the failing-first
  test pinning the fix, parametrized over both files above via `ALL_STAGE2`.

## Work breakdown

1. Independently verify the root cause against live data (not just trust
   webui's write-up): query `commits/{sha}/pulls` and the open-PR listing for
   3 real fork PRs on a public repo that actually receives them (`cli/cli`,
   since this repo has none). Confirm the divergence directly.
2. Write the failing test in `test_pr_review_fork_trust.py` asserting the old
   endpoint string is absent and the new one is present. Run it — confirm it
   fails on both parametrized paths (proves the test pins the real defect,
   not a phantom).
3. Apply the fix to `.github/workflows/pr-review-run.yml`: replace the
   `commits/$HEAD_SHA/pulls` query with `--paginate --slurp
   "pulls?state=open&per_page=100"` + `.[][] | select(...)`, the exact
   production-proven form from webui#338. Update the surrounding comment to
   explain why.
4. Apply the identical fix to
   `shared/templates/github-actions/claude-review-run.yml.template`.
5. Re-run the new test — confirm green on both paths.
6. Run the full existing suite for these files (`test_pr_review_fork_trust.py`,
   `test_pr_review_fail_closed.py`, `test_pr_review_workflow_shape.py`,
   `test_automerge_readiness.py`, `test_required_checks_drift.py`,
   `test_workflow_token_permissions.py`) — confirm no regressions.
7. Sanity-check both files still parse as valid YAML, and re-run the exact
   shipped jq pipeline against live data once more as a final behavioral
   check (not just a substring match).
8. Lint the changed test file.

## Test strategy

Structural/parsed-text assertions via the shared `_pr_review_workflows.py`
helpers (`shell_code()` — comment-stripped `run:` bodies), matching this
repo's existing convention for these two files rather than introducing a new
shell-execution test harness (webui's `_pr_review_shell.py` approach) for a
change this narrowly scoped. Real behavioral confidence comes from the live
API/jq probes against actual fork PRs recorded in the iterate spec's
Confidence Calibration, not from mocked fixtures — there is no fork PR on
this repository to drive an executed integration test against, and a mock of
GitHub's API shape would only encode the same assumption being tested.

No E2E / dev-server verification applies (see iterate spec's `## Verification`
— surface: none, justified).

## Alternative approach considered

**Alternative: keep `commits/{sha}/pulls`, and treat "0 matches" as "maybe a
fork PR" by falling back to a second API call scoped to search across all
repos (`GET /search/issues?q=...`) only when the first returns empty.**

**Rejected.** Two-call fallback logic is strictly more moving parts than
webui's one-call fix, for no behavioral gain — the open-PR listing already
finds same-repo PRs too (a same-repo PR's head is also in the base repo's
open-PR list), so there is no case the fallback would catch that the direct
listing does not already cover. It would also reintroduce exactly the kind of
first-try-then-fallback branching that this gate's own design notes (PR #437)
flag as the shape that hid bugs before ("the first draft... caught in
external review"). One query, one code path, already proven in production at
webui, is the simpler and more auditable choice for a required security gate.
