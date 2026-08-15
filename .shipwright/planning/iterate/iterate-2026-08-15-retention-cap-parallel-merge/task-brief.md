# Task brief: retention-cap parallel-merge race (small BUG iterate)

No iterate spec exists for this run (small complexity skips it). This brief is
the compliance target for review.

## Bug

`shared/scripts/tools/append_iterate_entry.py`'s `ITERATE_RETENTION = 50`
retention cap is computed per-worktree from whatever is on disk at append
time. Two iterates built in independent worktrees off the same `origin/main`
tip each independently evict the same oldest entry (deterministic sort over
an identical base set) and each add their own new one. A git merge accepts
the shared delete/delete and both unrelated adds, so the merged directory can
land one entry over cap per branch that overshot together in the same merge.
Measured 2026-08-13 in shipwright-webui: merging PR #365 into PR #366 left 51
tracked entries where the invariant claimed exactly 50.

## Two acceptable fixes offered by the operator (pick one, justify)

(a) Re-check at merge/periodically and trim to 50 newest when the merged
directory exceeds cap.
(b) Accept a bounded overshoot and DOCUMENT the invariant honestly as
"approximately 50, not exactly" -- including fixing
`append_iterate_entry.py`'s own docstring/comment, which stated the cap as if
it were exact.

Explicitly out of scope: the FR-/ADR-number collision family (same class,
different mechanism, tracked separately).

## Chosen fix: (b)

Key insight: `_apply_retention` already re-derives its eviction set from
`read_iterate_entries(project_root)` on every call -- i.e. from whatever is
actually on disk, not a private view of what this call itself wrote. So the
next `append_iterate_entry` call against an overshot merged directory (any
worktree, including a subsequent iterate off the repaired main) self-heals it
back to the cap. The overshoot is bounded (one entry per branch that raced
together) and self-healing, not an unbounded leak -- this was already true of
the existing code, only the documentation and a regression test are new.

## What changed

1. `shared/scripts/tools/append_iterate_entry.py` -- corrected the
   `ITERATE_RETENTION` constant's comment (and the module docstring's
   retention bullet) to state the cap is approximately 50, not exactly:
   pins (`iterate_retention_pins`) add on top of the unpinned window, and
   cross-worktree merges can overshoot by one unpinned entry per branch,
   self-healing on the next append.
2. `plugins/shipwright-iterate/skills/iterate/references/F5c.md` -- same
   correction to the retention section other iterate runs read at F5c.
3. `shared/tests/test_retention_merge_overshoot.py` -- new regression test:
   reproduces the merge overshoot at the filesystem layer (two identically
   seeded worktrees, each independently append+evict, then the git-merge
   outcome is simulated as base minus the one agreed delete plus both adds)
   and proves the self-heal (a subsequent append against the 51-file merged
   tree settles back to 50, keeping all three newest entries).
