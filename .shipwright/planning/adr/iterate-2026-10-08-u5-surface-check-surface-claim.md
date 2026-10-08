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

1. `none` without a closed `surface_none` reason code (`docs-only`, `test-only`,
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
   temporary index). A path changed by the branch, after filtering, is stale when
   its content in the verified commit differs from `tested_tree` and either:
   - its tested content differs from the staged head; or
   - a non-merge first-parent commit after the staged head touched it.

   Trunk merges and finalization records do not count. Evidence with no fingerprint
   is stale.

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
