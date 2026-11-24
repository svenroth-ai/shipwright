# Folding old event files at release (Step 5.3)

`tools/fold_events_for_release.py` (shared) is the routine housekeeping of `fold_events.py fold` made automatic. It runs
BEFORE Step 5.4, so the fold lands in a commit of its own and nothing of the release is staged yet, and BEFORE Step 5.5, so
the evidence documents are built from the folded tree. It never blocks the release: it prints one JSON object and exits 0.

## Reading the result

Add at most ONE line to the closing summary:

| `status` | meaning | print |
|---|---|---|
| `folded` | committed (`files`, `events`, `commit`) | how many files moved to the archive, `open_files` |
| `nothing_to_fold`, `not_applicable` | nothing old enough, or a project on the single event log | nothing |
| `skipped`, `incomplete`, `commit_failed` | `reason` says why; every failure after the fold started puts the tree back (`rolled_back: true`) | `reason` and `open_files`, then carry on |

## What it folds

Only files that are on the trunk unchanged and older than 14 days. The trunk is the repo's own (`origin/HEAD`, else
`origin/main`, else `origin/master`; `--base-ref` names another) and the plan uses `git merge-base <trunk> HEAD`, the set the
events integrity check accepts. A run in flight is never touched; a file (or the archive) with local changes is skipped.
Needs git 2.26 or newer (`--pathspec-from-file`). The fold commit is its own commit only when the release is merged
without squashing. The release notes come from the changelog drop files (Step 4), so a `chore(events)` commit never
appears in them.

## When something is wrong

- `rolled_back: false`: stop and repair before Step 6. Remove a left-behind `.git/index.lock` once no git runs, then
  `git reset -- .shipwright/events/drops .shipwright/events/archive` and `git checkout HEAD -- .shipwright/events/drops`. The archive
  stays until the drops are back (it may hold their only copy).
- Reverting a release: revert only the `chore(release)` commit, never the `chore(events)` fold commit (a revert deletes the
  archive, which the integrity check refuses as `deleted_existing`; the rollback of a fold is a fold, not `git revert`).

Contract: `docs/hooks-and-pipeline.md` → "Folding, quarantine and integrity".
