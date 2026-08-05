# Iterate Spec: fork PRs still fail Tier-3 PR review — resolver endpoint

- **Run ID:** iterate-2026-08-05-pr-review-fork-resolve
- **Type:** bug
- **Complexity:** medium
- **Status:** implemented
- **Risk flags:** `touches_ci_supplychain` (`.github/workflows/pr-review-run.yml`),
  `touches_public_api` (Stage-1 keyword false-positive from this run's own
  classify_intent message — no API route/exported type is touched; noted for
  the record, not chased further since `touches_ci_supplychain` already
  carries the enforcement floor this run needs)
- **Card:** trg-14d46892 (P3.02, split from anchor trg-bd66b9b0) + the finding
  folded into it, trg-94e71021 (backport of shipwright-webui#338)
- **Implements:** FR-01.17, restoring criterion (E)4/(E)5 for pull requests
  raised from a fork specifically

## Goal

`pr-review-run.yml` (Stage 2 of the two-stage Tier-3 PR review, PR #437,
2026-07-27) resolves the pull request number from the trusted event's head SHA
via `GET repos/{repo}/commits/{sha}/pulls`. That endpoint is scoped to the
**queried repository's own commit store**. A fork PR's head commit lives in the
**fork's** store, not the base repo's, so the query returns an **empty list**
for every fork PR — verified, not assumed (see Confidence Calibration). The
resolver's own ambiguity guard then reads "found 0 matches" and refuses to
post a verdict, so a fork PR does not merely go unreviewed — it gets a hard
`failure` status on the required `PR Review` context and can never merge. This
is the exact case the two-stage split exists to fix (FR-01.17 (E)4/(E)5:
review a fork PR safely), inverted into an availability regression that no
same-repo PR would ever reveal, because this repository has never received an
actual fork PR to surface it.

The same defect is duplicated in `shared/templates/github-actions/claude-review-run.yml.template`,
the Stage-2 template scaffolded into every adopted repo — both files share the
same resolver shape by design (`shared/tests/_pr_review_workflows.py`
parametrizes `ALL_STAGE2` over both), so both carry the bug and both need the
same fix.

**Origin.** `shipwright-webui` PR #338 ported the two-stage split and, in the
process, found and fixed this defect (doubt-reviewer finding 26, its own
iterate `iterate-2026-07-31-two-stage-pr-review`). Filed back here as triage
`trg-94e71021`, folded into anchor `trg-bd66b9b0`, and inherited by this run's
assigned unit (P3.02 / trg-14d46892) when the anchor's original ask — "build
the two-stage split" — turned out to already be delivered by PR #437 before
the anchor was even written. This run narrows scope to the one thing PR #437
did not yet have: **the fork-PR resolver fix**, ported from webui#338's proven
form. webui#338 carries five further hardening divergences beyond this one
(force-push-history re-check, an impostor-check-run guard, `!cancelled()` vs
`always()`, `persist-credentials: false`, a wider sensitive-path set); those
are out of scope for this run and are recorded as a separate triage finding
(see F12 summary) rather than folded in here.

## Acceptance Criteria

- [x] AC1. Stage 2's resolve step (both `.github/workflows/pr-review-run.yml`
  and `shared/templates/github-actions/claude-review-run.yml.template`) no
  longer queries `commits/{sha}/pulls`. (E)
- [x] AC2. Stage 2's resolve step lists the base repository's **open** pull
  requests (paginated) and matches on `.head.sha`, so a fork PR's head SHA is
  found exactly as reliably as a same-repo PR's. (E)
- [x] AC3. The existing ambiguity guard (`count -ne 1` → fail closed) is
  unchanged in shape and behavior for the same-repo case — this is a data
  source swap, not a policy change. (E)
- [x] AC4. `shared/tests/test_pr_review_fork_trust.py` pins the fix: fails
  against the pre-fix resolver, passes against the post-fix one, parametrized
  over both Stage-2 files.

## Spec Impact

- **Classification:** NONE
- **Justification:** FR-01.17 already requires every proposed change —
  including one from "the author's machine" outside the maintainer's control,
  which reads as covering forks — to be independently reviewed on the host.
  This fix restores that already-correct requirement for the one case it
  structurally could not reach (fork PRs); the requirement's text does not
  change. `@FR-01.17` tags already cover the touched tests.

## Out of Scope

- The five further webui#338 divergences beyond the resolver fix (see Goal) —
  recorded as a new triage finding for a future IT-9 unit, not built here.
- UNIT 1 (P3.01, oversize-diff fail-closed) and UNITS 3-6 of the IT-9 split —
  separate cards, separate runs; IT-9's serial-ownership rule means this run
  touches only the resolver block.
- Re-deriving webui#338's other test infrastructure
  (`_pr_review_shell.py`-style executed-shell tests) — this repo's existing
  convention for these files is structural/parsed-text assertion
  (`_pr_review_workflows.py` + `shell_code()`), which is what the new test
  uses.

## Design Notes

No UI; Design Check Tier 2 (markdown) — n/a, no screens. Two workflow files
change one `run:` block each; a comment block explains the fix and cites the
finding it closes.

## Affected Boundaries

No new producer/consumer pair — the resolve step's *source* changes (which
GitHub REST endpoint supplies the candidate list) but the shape it hands to
the rest of the step (a JSON array of PR numbers, `jq`-filtered to zero-or-one)
is unchanged. `touches_io_boundary` does not fire. n/a.

## Confidence Calibration

- **Boundaries touched:** none (see Affected Boundaries).

- **Empirical probes run:**
  - *Does `commits/{sha}/pulls` really return empty for a fork PR, on this
    exact API path, today?* Verified directly (not assumed from webui's
    write-up): fetched 3 real open cross-repository PRs on `cli/cli`
    (`gh api graphql` filtering `isCrossRepository: true`, PRs #14083/#14082/#14081)
    and queried `repos/cli/cli/commits/{headRefOid}/pulls` for each — all
    three returned `[]`.
  - *Does listing open PRs and matching `head.sha` actually find them?*
    Verified against the same 3 PRs: `gh api --paginate
    "repos/cli/cli/pulls?state=open&per_page=100"` filtered on `.head.sha ==
    $sha` returned exactly one match each — `[14083]`, `[14082]`, `[14081]`.
  - *Does the exact jq expression shipped in the fix evaluate correctly?* Ran
    the literal `--paginate --slurp` + `.[][] | select(...)` pipeline from the
    committed diff against live data for PR #14083 — returned `[14083]`.
  - *Does `--paginate` (no `--slurp`) already auto-flatten array-returning
    endpoints, making `--slurp` + `.[][]` redundant?* Probed empirically
    (per_page=20 to force multiple pages): yes, on `gh` 2.92.0, plain
    `--paginate` already returns one flattened array across pages. Kept
    `--slurp` + `.[][]` anyway rather than "simplify" — it is the exact
    production-proven form from webui#338, and the alternative would trade a
    verified-safe pattern for an unverified assumption about `gh` version
    stability, in a required security gate. Not a behavior difference, a
    provenance choice.

- **Test Completeness Ledger:**

  | # | Testable behavior | Disposition | Evidence / reason_code |
  |---|---|---|---|
  | 1 | Stage 2 (monorepo `pr-review-run.yml`) no longer queries `commits/{sha}/pulls` | tested | `test_pr_review_fork_trust.py::test_stage2_resolves_a_fork_pr_not_just_a_same_repo_one[path0]` PASSED |
  | 2 | Stage 2 (shipped `claude-review-run.yml.template`) no longer queries `commits/{sha}/pulls` | tested | same test, `[path1]` PASSED |
  | 3 | Stage 2 resolves identity by listing open PRs and matching `head.sha` (both files) | tested | same test, both params — asserts `pulls?state=open` present |
  | 4 | The ambiguity guard (exactly-one-match, fail closed on 0 or many) still holds after the data-source swap | tested | `test_stage2_refuses_an_ambiguous_pull_request[path0,path1]` PASSED (pre-existing test, unmodified, still green) |
  | 5 | The force-push re-check, artifact-distrust, and no-checkout-of-PR-head rules are untouched by this edit | tested | full `test_pr_review_fork_trust.py` + `test_pr_review_fail_closed.py` suites PASSED (37 passed, 1 pre-existing skip unrelated to this change) |
  | 6 | The fix's actual GitHub-API behavior against real fork PRs (not a mock) | tested | live probe against 3 real fork PRs on `cli/cli`, see Empirical probes above — `covered-by-existing-test` does not apply, this *is* the primary evidence, captured as a probe because no fork PR exists on this repo to drive an executed CI run against |
  | 7 | YAML stays syntactically valid after the edit (both files) | tested | `yaml.safe_load()` on both files, no exception |
  | 8 | No injection / secrets-handling regression introduced by the edit | tested | `test_pr_review_workflow_shape.py::TestHardening` (SHA-pin + no-raw-`${{ github.* }}`-in-run-body) PASSED unmodified |

- **Confidence-pattern check:** Asymptote (depth) — no prior "are you
  confident?" question in this run produced a "yes" that was later
  contradicted; this is the first and only probe round, and it already found
  the real defect (empty list from the old endpoint) rather than confirming a
  false negative, so no further probe is owed. Coverage (breadth) — 8/8 ledger
  rows `tested`, 0 untested-testable.

## Doubt-Review Findings (Stage 3)

Three low-severity doubts, all confirmed **fail-safe-only** (never a false
success) — addressed in writing per the advisory-must-address contract, no
code change required for any of the three:

1. **A same-repo head-move race now fails one step earlier, with a less
   specific message.** The old `commits/{sha}/pulls` query resolved by commit-
   history membership, so it tolerated the head moving between Stage 1 firing
   and Stage 2's resolve step running, and let the run reach the later
   "head moved during the run" recheck. The new `pulls?state=open` +
   `.head.sha` query requires the CURRENT head to equal the event SHA, so that
   same (narrow, same-repo-only) race now fails at the resolve step itself
   with "could not determine whether a review was required" instead. Both
   paths land on `state=failure` on the same SHA — no false success, just a
   less specific diagnostic in an already-rare window. Accepted as-is; AC3's
   "unchanged... not a policy change" refers to the `-ne 1` guard's logic
   (verified byte-identical), not to which upstream race produces which
   message.
2. **Offset-pagination page-boundary drift on a repo with >100 concurrently
   open PRs experiencing churn mid-fetch could in theory produce a false
   "0 matches" or "ambiguous" failure.** This risk did not exist with the old
   single, non-paginated request. It is new, and it is real, but it can only
   ever *deny* a review, never wrongly grant one — and the empirical probe
   against `cli/cli` (a genuinely high-churn, >100-open-PR repo, `per_page=100`
   forcing real multi-page fetches) found no drift across 3 live runs. Accepted
   as an out-of-scope, fail-closed-only edge case; not worth a mitigation
   (e.g. retry-with-backoff) for a defect this narrow.
3. **Is there a second, unfixed instance of the same defect?** Checked:
   `shared/scripts/tools/main_health_gh.py:pr_for_commit()` also queries a
   `commits/{sha}/pulls`-shaped endpoint and is untouched by this diff. Its
   only caller (`main_health.py`'s self-heal path) always passes a SHA already
   landed on the default branch — exactly the case where that endpoint IS
   reliable (a commit on the default branch has at most the one PR that merged
   it, findable in its own history). Not the fork-PR case this run fixes; no
   second instance found.

## Verification (medium+)

- **Surface:** none
- **Runner command:** n/a
- **Evidence path:** n/a
- **Justification (surface=none):** This change edits a GitHub Actions
  workflow's shell body; there is no startable dev server, CLI entrypoint, or
  API surface for this repository's own CI plumbing to exercise locally as an
  E2E run — the only real verification is the workflow executing on GitHub
  against an actual fork PR head, which is outside what F0.5 can drive.
  Empirical confidence instead comes from the live-data jq/API probes recorded
  under Confidence Calibration (run against real `cli/cli` fork PRs, the
  identical class of input this fix must handle) plus the executed pytest
  suite pinning the workflow's parsed structure.
