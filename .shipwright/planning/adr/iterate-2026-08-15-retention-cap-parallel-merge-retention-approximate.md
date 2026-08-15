# Retention cap is approximate, not exact, under parallel worktree merges

## Context

`shared/scripts/tools/append_iterate_entry.py`'s `ITERATE_RETENTION = 50`
retention cap assumed serialized appends. The append transaction serializes
appends within one worktree via a `file_lock`, but two iterates built in
independent worktrees off the same `origin/main` tip each compute retention
from an identical base set they cannot see each other's write into: both
evict the same oldest entry (deterministic `sort_key` over identical input)
and both add their own new one. Git merges the shared eviction as an agreed
delete/delete (no conflict) and both adds as unrelated new files (no
conflict), so the merged directory can land one entry over cap per branch
that overshot together in the same merge.

Measured 2026-08-13 in shipwright-webui: `iterate-2026-08-13-mission-mobile-visual`
and `iterate-2026-08-13-changelog-manifest-config` were built in parallel
worktrees off the same origin/main tip. Retention independently evicted the
same oldest file (`iterate-2026-07-20-triage-write-fs-race.json`) on both
branches. Merging PR #365 into PR #366 left 51 tracked entries where the
invariant claimed exactly 50.

This is the same class of problem as the known FR-number / ADR-number
collisions across parallel iterates — two branches computing a decision from
a shared tip that only one of them can be right about — but a different
mechanism, and explicitly out of scope here. That family is tracked
separately and this run does not widen into it.

## Two candidate fixes

**(a) Re-check at merge or periodically.** Trim the directory to the 50
newest by date whenever it is found to exceed the cap (e.g. on the next
append, or via a dedicated merge-time / periodic sweep). Would require new
machinery — this framework has no merge-time hook, and a periodic sweep is a
new scheduled surface — to guard against an overshoot that, per the
investigation below, already self-corrects.

**(b) Accept a bounded overshoot and document the invariant honestly** as
"approximately 50, not exactly" — including fixing the code's own
comment/docstring, which stated the cap as if it were exact.

## Decision

Chose **(b)**, discovered during investigation that it requires no new
machinery: `_apply_retention` already re-derives its eviction set from
`read_iterate_entries(project_root)` on **every** call — i.e. from whatever
is actually on disk, not a private view of what that specific call itself
wrote. This means the very next `append_iterate_entry` call against an
overshot merged directory (in any worktree, including a subsequent iterate
off the repaired main) reads the full merged state and trims it back to the
cap. The overshoot is therefore:

- **bounded** — at most one unpinned entry over cap per branch that
  overshot together in the same merge, and
- **self-healing** — resolved automatically by the next append, with no
  operator action and no new code path.

This was already true of the pre-existing code. Only the documentation
(which promised an exact cap the code could never hold under a parallel
merge) was wrong, and only the documentation needed to change.

## What changed

1. `shared/scripts/tools/append_iterate_entry.py` — the `ITERATE_RETENTION`
   constant's comment (and the module docstring's retention bullet)
   now state the cap is approximately 50: pins (`iterate_retention_pins`)
   are kept on top of the unpinned window and are never eviction
   candidates, and cross-worktree merges can overshoot the unpinned window
   by one entry per overshooting branch, self-healing on the next append.
2. `plugins/shipwright-iterate/skills/iterate/references/F5c.md` — the
   retention section other iterate runs read at F5c carries the same
   correction, with a "Why 'approximately,' not 'exactly'" explanation of
   the mechanism.
3. `shared/tests/test_retention_merge_overshoot.py` — new regression test.
   `test_two_independent_worktrees_merge_one_over_cap` reproduces the
   incident at the filesystem layer (two identically seeded worktrees each
   independently append+evict; the merge outcome is simulated as the base
   minus the one agreed delete plus both branches' adds) and asserts the
   merged directory lands at exactly cap+1.
   `test_next_append_on_the_merged_tree_self_heals_to_cap` then appends once
   more against that 51-file tree and asserts it settles back to the cap,
   with all three newest entries (both branches' plus the new one)
   surviving.

## Consequences

- No new merge-time or periodic re-check machinery is added; the fix is
  purely documentation plus a regression test proving the pre-existing
  self-heal.
- The retention invariant now reads honestly everywhere it is stated: the
  code comment, the module docstring, and F5c.md all agree the cap is
  approximate under parallel merges, not exact.
- If a future change ever removes or weakens the "re-read the full
  directory on every call" behavior in `_apply_retention`, the self-heal
  claim (and this decision) would need to be revisited — the regression
  test would catch that regression directly.

## Review

Reviewed by the standard cascade for this iterate (spec-reviewer,
code-reviewer, external code-review via OpenRouter/openai). Two rounds:
the first spec-reviewer pass rejected an early version of this fix for
overstating the guarantee (ignoring `iterate_retention_pins`); the first
code-reviewer pass requested changes for a bloat-baseline exception that
did not match the repo's established ADR-reference convention and for
duplicated explanation across three files. Both were fixed and re-reviewed
to a clean pass before commit.
