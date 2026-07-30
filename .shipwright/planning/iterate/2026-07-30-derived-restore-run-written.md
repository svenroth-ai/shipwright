# The run's own ledger survives finalization

**Run-ID:** `iterate-2026-07-30-derived-restore-run-written`
**Type:** change · **Complexity:** medium
**Split from:** `iterate/derived-snapshots-refresh` (parked; the post-merge refresh
producer is a separate, still-open decision). This branch was carved out so the fix
below could land while that architecture question stays open.

## The defect

Eleven paths are DERIVED_SNAPSHOTS: shared views an iterate must not commit, because
every branch rewrites all of them regardless of what it changed, so N open PRs collide
N(N-1)/2 times on files carrying no information about any of the changes. To keep the
worktree clean, `restore_derived_to_head` resets any dirty one to `HEAD`.

**One of the eleven is not derived at all.** `shipwright_test_results.json` holds the
F5 ledger — `iterate_latest`, the test totals, `test_completeness`,
`surface_verification` — and the RUN writes it. No producer can recompute it. Resetting
it is not undoing a regeneration; it is deleting the run's evidence, and it did so
silently: two sessions reported it independently, one had its F5 block overwritten
twice in a single run, and a landmine note in the operator's memory had already failed
to prevent a third.

A second defect of the same shape sat in the test suite. `test_fold_map_e2e` and the
RTM deep-link test asserted EQUALITY against committed artifacts that #480 had frozen,
so a branch minting a requirement had exactly two options: fail the test, or commit an
artifact the F11 gate forbids. Adding a requirement could not pass CI at all.

## Why the obvious fix is only half an answer

Excluding the path from the restore protects its content and leaves it
tracked-and-dirty — and a dirty path is what makes `git merge` refuse to START once
mainline moved it (`Your local changes to the following files would be overwritten by
merge`, exit 2). `ensure_current` then returns exit 6 and no branch advances.

The first draft of the carve-out argued that trigger could not fire, on the premise
that nothing commits `shipwright_test_results.json` any more. **The premise is false**,
and this was measured rather than reasoned about:

- `main` still TRACKS the file, and its copy still moves — one of `main`'s twelve most
  recent commits on 2026-07-30 (#497) changed it, because the commit gate inspects a
  single commit and a multi-commit PR can carry it past.
- Reproduced in a throwaway repository: mainline moving the path while the worktree
  copy is dirty aborts the merge exactly as described.

So both failures are real and mutually exclusive. Restore it and the evidence dies;
leave it and the pipeline stops.

## What changed

**The bytes are CARRIED across the merge** (`shared/scripts/lib/run_written_ledger.py`).
`stash_run_written` reads the content and hands git a clean path; `unstash_run_written`
writes it back. Every state that has bytes anywhere is taken, and the clean-up matches
where they were: a tracked path via `git checkout HEAD --` (index and worktree
together, so a staged ledger cannot ride into the merge commit either), an UNTRACKED
one via `unlink`, an `MD` out of the index via `git show :<path>`. Only a plain
deletion is passed over, because it has no bytes in either place.

**The write-back is in a `finally`, and its placement is load-bearing.**
`git merge --abort` is `git reset --merge`, which ALSO refuses when a path differing
between `HEAD` and the index carries unstaged changes. A write-back placed before the
abort paths breaks them — measured: `error: Entry '<path>' not uptodate`, exit 128,
`MERGE_HEAD` left standing — and two of those aborts ran `check=False`, so the failure
was swallowed and reported as "merge aborted; resolve by hand" over a wedged tree.

**Nothing fails silently.** Both functions return what they could NOT do, and the
caller names it (`ledger-not-carried`, `ledger-writeback-failed`); a failed write-back
returns a non-`ok` status rather than reporting success over a lost ledger. That is the
whole lesson of the defect: the cost was never the failure, it was that the failure
looked exactly like success.

**Three `integrate_main` modules, split on what a failure is allowed to do.**
`integrate_main` owns the brackets (resolve the ref, carry the ledger);
`integrate_merge` owns the window where nothing has landed and every bad outcome ends
in a VERIFIED `git merge --abort`; `integrate_regenerate` owns what follows the merge
commit, where there is nothing left to abort. Two abort sites that previously claimed
an abort without checking it now go through one helper that re-reads `MERGE_HEAD`.

**The frozen-artifact assertions are one-directional** where #480 forced it, with a
non-vacuity floor on both sides, and each test states what it stopped catching.

## Acceptance criteria

- (E) Given mainline has moved `shipwright_test_results.json` and the worktree copy is
  dirty, when `integrate` runs, then the merge succeeds AND the file still holds THIS
  run's ledger, unstaged.
- (E) Given a non-churn conflict, when the merge is aborted, then `MERGE_HEAD` is
  really gone before `blocked` is returned, and the ledger is back on disk.
- (E) Given mainline deleted the path, when `integrate` runs, then the ledger is
  recreated untracked rather than lost.
- (E) Given the ledger cannot be read or written back, when `integrate` runs, then the
  result NAMES it and a failed write-back does not report `ok`.
- (E) Given an `MD` ledger, when `integrate` runs, then the index copy is carried and
  the staged deletion is cleared.
- (E) Given this repo's committed traceability artifacts are frozen, when a fresh
  derivation is compared against them, then a LOST requirement fails and an added one
  does not — with both sides asserted non-empty.
- (E) Given a retry budget whose deadline rounds a hair above it, when the sleep is
  clamped, then it never exceeds the budget the caller configured.

## Review

Full cascade, three stages, re-run until clean: `spec-reviewer` (PASS after three
rounds), `code-reviewer` (8 findings), `doubt-reviewer` (12 objections, adversarial).
Each stage found at least one real defect in code that had already passed the previous
one; the abort-ordering bug and the false premise above were both reviewer finds, and
both were then measured rather than accepted on argument.
