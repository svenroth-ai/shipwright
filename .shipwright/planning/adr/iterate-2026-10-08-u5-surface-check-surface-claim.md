# The F0.5 surface claim is re-derived from the diff and the staged evidence

Run: `iterate-2026-10-08-u5-surface-check` (campaign
`2026-10-07-finalization-claims-hardening`, unit U5).

## Context

At medium+, F11 checked the shape of the F0.5 block only. `surface="none"` with any
free-text justification passed, even when the diff added an API route, and
`tests_run` / `exit_code` were typed numbers nothing compared with an execution
record.

## Decision

`verifiers/surface_check.py` (re-exported from `iterate_checks.py`) refuses, at medium+:

1. `none` without a closed `surface_none` reason code (`docs-only-surface`, `test-only`,
   `build-config-only`, `no-behavior-change`, `no-startable-surface`). The producer
   `surface_verification.py --reason-code` validates the code too.
2. `none` while the merge-base diff touches a runnable surface. `_surface_detect.py`
   detects UI sources (reusing `detect_frontend_changes`), API routes / controllers /
   handlers (`route`, `router` count), SSE / WebSocket modules, and message contracts.
   It checks both paths and content (the changed lines plus the full file at the
   commit, read by `_surface_git.py`). Tests, fixtures and prose never count. The diff
   wins over the code. A diff that cannot be measured confirms nothing.
3. A UI change recorded as anything but `web`.
4. Any other surface whose numbers the staged evidence does not back
   (`_surface_evidence.py`). This covers six cases:
   - evidence is absent, or another run's;
   - `head_commit` is not the verified commit or one of its ancestors;
   - a `web` surface has no Playwright report;
   - a detected surface's `cli` / `api` runner names no test files;
   - a staged test failed;
   - fewer tests passed than `tests_run`, or a path named in the runner has no passing result.
5. Stale evidence (`_surface_revision.py`). Staging records `tested_tree`, the git
   tree id of the working tree at staging (`lib/worktree_tree.py`, built in a
   temporary index). The branch owns the paths the tested tree changed against the
   staged head plus those its own first-parent non-merge commits after that head
   touched. For each owned path P, `tested_tree:P` must equal `L(P):P`, where L(P)
   is the newest of those commits that touched P (the staged head if none did).
   F11 merges the trunk (`ensure_current`) before it verifies, so the verified
   commit may hold a sibling's hunks in a file this branch also edited. Comparing
   with the branch's own last write leaves those hunks out, whichever side of its
   own commit the unit staged on. A later fix commit or an amend is that last write,
   so it still differs. Not counted: tests and prose, finalization records, and a
   path only the tested tree has (absent at the staged head and the commit, e.g. a
   stray untracked file; named in the pass detail). When the staged head is not an
   ancestor (a soft-reset consolidation), the tested tree must equal the commit on
   every branch-changed path. Evidence with no fingerprint is stale.
6. Reports older than the code (`lib/_evidence_drop_guard.py`). `evidence_drop.stage`
   refuses, and stages nothing, when a branch-changed file was modified after the
   oldest report being staged was written. The F11 repair text says to re-run the
   tests and then stage; it no longer offers the bare stage command as the fix.
7. Result scope (`_surface_runner.py`). When the runner names test paths (a `cd <dir>
   &&` prefix, `--directory` / `--project <dir>` and absolute paths under the project
   are understood), the count and the "no failing result" rule look only at results
   under them, and a later staged report's verdict for a test id replaces an earlier
   one (a staged retry). A runner that names no path is checked over the whole staged
   suite, fail-closed, and the detail says so.

## Rejected

- Parent-only freshness (`head_commit` must be the parent of the verified commit).
  A probe against U1, U3 and U4 showed it would break every real campaign unit.
  Review-fix commits, 3f-bis record commits and trunk merges all follow the staged
  head.
- Commit-walk freshness (no counted commit after the staged head). It cannot see
  an amend after staging, which the first commit's own content hides. The
  fingerprint can.
- A producer-side `--require-reason-code`. The producer does not know the run's
  complexity; F11 is the gate.
- Letting an unmeasurable diff pass a non-`none` surface. Kept fail-closed: the
  surface binding needs the diff.

## Accepted limits

- The threat model is an honest agent taking a shortcut, not forgery. The staging
  directory is gitignored and unauthenticated, so anyone who can write files can
  write a provenance sidecar that passes.
- The fingerprint is taken at staging, not when the tests ran. Decision 6 bounds the
  gap: reports older than a branch-changed file are refused at staging. A deletion
  has no mtime and is not seen there.
- A command-line interface is not a detected surface kind. An `argparse` / `click`
  change can still record `none` with `no-behavior-change`.
- Submodule content is seen only as its gitlink (the commit it points to), never as
  the files inside it.
- A conflict resolution inside a trunk-merge commit is not a branch write, so it does
  not make evidence stale.

## Sequencing (campaign)

After U5 merges, any sibling unit that commits a code fix after staging must re-run
F0 and stage again. Re-staging the old reports is refused (decision 6), and the old
evidence reads stale at F11 (decision 5).

## Consequences

After a code fix commit (for example a 3f-bis review fix), a unit must re-run F0 and
stage evidence again, or the medium+ surface check reads stale. Detection is
conservative: `router.py` counts. When in doubt, drive the change as `cli` with a
runner that names its test files. Known blind spot: a surface reached only through
a file the diff does not touch (for example a decorator applied elsewhere) is not
detected.

## Reviews

- **Architecture review: approve / approve.** Both GLM findings were accepted:
  - reuse the frontend detector;
  - stale rules fail open: detection was made conservative and the blind spot is documented.
- **Plan review: openai revise, glm approve.** Accepted:
  - the ancestor-staleness gap (fixed with the fingerprint);
  - `route` / `router` were excluded and now count;
  - bind the evidence to the detected surface;
  - a precedence test and a same-commit evidence test.
- **External code review: openai revise, glm revise.** Accepted:
  - full-file content is scanned, not only changed lines;
  - the first-commit exemption could be bypassed (fixed with the fingerprint);
  - api evidence is now tied to the surface through the runner's test paths;
  - a weak attribution assertion and a vacuous wiring test were strengthened.

  Rejected, with the reasons above: the producer `--require-reason-code`, and letting
  an unmeasurable diff pass a non-`none` surface.
- **PR review (#846), all accepted:**
  - freshness against trunk merges (decision 5);
  - re-staged old reports (decision 6);
  - stray tested-only paths and soft-reset consolidation (decision 5);
  - result scope, retries and runner directories (decision 7);
  - wider detector signals: framework routes, `.d.ts`, contract data files, templates;
  - `cat-file` parsing that never splits a path.

  CLI detection was declined and recorded as an accepted limit.

## Confidence calibration

Four probes were run:

1. The detector over every tracked file. Found `router` / `triage_route` hits, which
   were kept as conservative true positives.
2. Real sibling evidence on U1, U3 and U4. Found that the parent rule broke every
   unit. Fixed.
3. The pass path on real F6 commits: 18k staged results checked in 0.8 s. No finding.
4. A producer CLI round trip covering CRLF, non-ASCII text and a closed code, then
   a route commit, which was refused. No finding.

The asymptote was reached after two consecutive probes without a finding.
`working_tree_id` takes about 1 s on this worktree.
