# Mini-Plan: triage-backlog-outbox-routing

- **Run ID:** iterate-2026-08-06-triage-backlog-outbox-routing

## Files to create/modify

1. `shared/scripts/tools/ensure_current.py` (edit) — new
   `_absorb_dirty_triage_log()` helper + one call site, right before the
   merge is attempted (only reached when the branch is behind).
2. `shared/tests/test_ensure_current.py` (edit) — two new tests:
   the reported-bug regression (real dirty tracked file + real divergent
   origin content + real merge + real churn resolver) and a clean-tree
   sanity check.

## Work breakdown

1. Reproduce the exact reported git error in a test, against the CURRENT
   (unfixed) `ensure_current.py` — confirms the failure mode before
   touching production code.
2. Add `_absorb_dirty_triage_log`: `git status --porcelain` scoped to
   `.shipwright/triage.jsonl`; if dirty, `git add` + `git commit` that one
   path (never `-A`) with a `chore(triage): absorb background triage
   writes` message. Never raises — matches every other helper in this
   file's error posture.
3. Wire the call into `ensure_current()`, only in the "behind, about to
   integrate" branch (a no-op branch never reaches a merge, so nothing to
   absorb there).
4. Re-run the new test — GREEN. Re-run the full `test_ensure_current.py`
   + `test_integrate_main.py` + `test_integrate_campaign_status.py` suites
   — no regressions (16/16 passed).

## Data model changes

None.

## Test strategy

Real git repos (`git_origin_repo` + `make_worktree` fixtures already used
by the sibling tests in this file), not mocks — the whole point is proving
a REAL `git merge` no longer refuses and the REAL churn resolver still
reconciles divergent content. E2E/UI: n/a (no surface).

## Alternative Approach (medium, mandatory)

**Considered:** route the compliance-backlog producer's rolling
`compliance:backlog:<sig>` card to the gitignored outbox unconditionally
(add `require_default_branch: bool = True` to `triage.should_route_to_outbox`,
pass `require_default_branch=False` from the one producer call site), so
the producer's per-Stop dismiss+append refresh never touches the tracked
`triage.jsonl` while on an iterate branch — eliminating the dirty-tree
precondition at its source instead of coping with it at the merge.

**Built and tested first.** TDD cycle completed (RED tests proving the
original bug, GREEN after the fix), full `shared/tests` suite run
(8528 passed / 1 failed), Stage-1 spec-reviewer PASS after two fix rounds.

**Rejected because a Stage-2 code-review pass found it structurally
unsound, not merely imperfect:**

1. **Half-applied.** The fix routed the producer's APPEND to the outbox
   but the DISMISS path (`triage_bundle.py`'s `_dismiss` → `triage.mark_status`)
   still used the DEFAULT branch-gated probe. Any backlog item the
   worktree-setup D2 sweep had already materialized into the tracked log
   (the normal state at run start) would still get its refresh status
   line written to tracked triage.jsonl — the exact bug, not fully closed.
2. **Introduced a silent data-loss hazard.** During an iterate run,
   `should_route_to_outbox`'s branch check resolves to the WORKTREE, not
   the main tree. Nothing sweeps a worktree's own outbox into its own
   branch (`sweep_outbox_to_branch` only ever reads `main_root`'s outbox,
   at worktree SETUP), and F11 deletes the worktree (`git worktree remove`)
   on completion. So the compliance backlog's mid-run activity would be
   silently discarded every iterate run — a hazard this exact repo had
   already named and fixed the DAY BEFORE this run, in a sibling context
   (`.shipwright/agent_docs/conventions.md`, entry
   `iterate-2026-08-05-wire-local-guard-scripts`: *"a session in
   `.worktrees/<slug>` resolves the worktree, whose outbox no sweep reads
   and which is deleted with the tree"*). The rejected fix reintroduced
   precisely that.
3. **Missed the required same-diff doc update** to
   `docs/hooks-and-pipeline.md`'s artifact-write matrix, which the change
   would have made false.

**Why the chosen fix avoids all three:** it does not touch
`should_route_to_outbox`, the producer, or any outbox semantics at all —
so there is no append/dismiss split to keep in sync, and no worktree-outbox
delivery question to answer. It targets the ACTUAL failure point (the
pre-merge dirty-tree check) directly, reusing the churn resolver that
already exists specifically for `triage.jsonl` divergence, and is
~25 lines in one already-small (177-line, no bloat-baseline entry) file
instead of touching a widely-shared, already-at-its-frozen-cap primitive
(`triage.py`, 882/882 lines, `ADR-121` exception) used by six-plus call
sites across `shared/` and multiple plugins.
