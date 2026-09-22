# Bloat exception — `shared/tests/conftest.py` raised to 323-LOC

<!-- Named by run_id per `_template-bloat-exception.md` — this heading does
     NOT claim a numeric ADR-NNN; that identity is assigned later, at
     release, by decision_log.md. `shipwright_bloat_baseline.json`'s entry
     for this file is set to `"state": "exception", "adr": "ADR-pending:
     .shipwright/planning/adr/iterate-2026-09-22-r3-review-diff-fix-conftest-bloat-exception.md"`,
     superseding its prior `"ADR-101"` reference for the `current` field
     only — ADR-101 remains the record of the FIRST crossing (296→320);
     this is the second, on top of it. -->

- **Status:** accepted
- **Date:** 2026-09-22
- **Re-Review-Date:** 2026-12-22
- **Incident Reference:** `iterate-2026-09-22-r3-review-diff-fix`
  (campaign-dag-scheduler R3). CI (`gh pr checks` on PR #787) surfaced 34
  test failures across four R3-added test files, all `git commit` exit 128
  ("Please tell me who you are") — the shared `git_origin_repo` fixture's
  identity env vars were wired only into its own internal `_git()` closure,
  never persisted into the cloned repo's local `.git/config`, so any test
  file's own separately-defined `_commit_file()` helper (a bare
  `subprocess.run(["git", "-C", repo, "commit", ...])` with no `env=`) relies
  on ambient global git config — present on the author's dev machine, absent
  on GitHub's runners.

## Context

Two lines (`_git(work, "config", "user.email", ...)` /
`_git(work, "config", "user.name", ...)`) plus a one-line comment, added
right after the fixture's `clone` call, push the file from 320 to 323.

## Ousterhout Argument

Unchanged from ADR-101: this is still one deep module — a single fixture
hiding the bare/clone/env setup every hermetic git test needs behind a
two-line interface (`git_origin_repo(tmp_path)` yields `(work, origin)`).
The fix adds to that same interface's guarantee (a working, committable
repo) rather than a new responsibility.

## YAGNI Check

Nothing speculative: exactly the two `git config` calls the failing CI log
demands, no broader identity-management abstraction.

## Chesterton's Fence

The fixture's existing `env` dict (scoped to its own `_git()` closure) was
deliberate — it isolates the fixture's OWN init/clone/push calls from the
caller's ambient config. It was never meant to reach callers' own git
invocations; that gap was latent, not a fence to preserve.

## Decision

`current` raised from 320 to 323. No further growth is anticipated on this
line — the fix is complete once these two lines land.

## Consequences

Every `shared/tests` file relying on `git_origin_repo` for a hermetic repo
now gets a committable identity for free; no consumer changes required.

## Rejected alternatives

- **Trim the added comment to fit under 320**: tried first — even a
  single-line comment left the file at 322 (2 over); the calls themselves
  are 2 lines with zero comment possible below that. Codegolfing (e.g. a
  one-line loop over `(key, value)` pairs) was rejected as it reads worse
  for zero LOC benefit once the `for` line and its body are counted.
- **Have every consuming test file's own `_commit_file()` pass its own
  `env=`**: rejected — that repeats the same three lines across four files
  instead of once in the shared fixture, and a fifth future test file would
  silently reintroduce the bug.
