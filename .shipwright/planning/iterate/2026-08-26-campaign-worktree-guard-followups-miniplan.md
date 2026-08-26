# Mini-Plan: campaign-worktree-guard-followups

## Work Breakdown

1. `lib/campaign_session_lock.py` (new) — heartbeat lock: `acquire` /
   `touch`, keyed on `session_id`, guarded by the existing `lib.file_lock`
   for the read-modify-write critical section.
2. `checks/check_campaign_session_lock.py` (new CLI) — `acquire`/`touch`
   subcommands, exit 0/1 + `--json`, matching `check_worktree_location.py`'s
   existing contract shape.
3. `lib/worktree_location.py` — add optional `expected_campaign_slug` to
   `worktree_location_error`; branch-prefix check via the already-shared
   `lib.worktree_isolation.current_branch`.
4. `checks/check_worktree_location.py` — thread `--campaign-slug` through.
5. Docs: `campaign-worktree.md` (Setup + spawn-guard + defense-in-depth
   sections; remove both closed "Known limitations" bullets),
   `campaign-mode.md` (step 0 pointer + step 3a touch, within the 400-LOC
   budget), `sub-iterate-runner.md` (Step 1.0 `--campaign-slug`),
   `docs/hooks-and-pipeline.md` (parity paragraph).
6. Tests: unit (lock semantics, identity-check semantics) + one real-
   subprocess integration test composing both guards around the actual
   `setup_iterate_worktree.py` producer — the `cross_component` ledger row.

## Alternative Approach Considered (and rejected)

**Reuse `lib/host_resource_lease.py` for the session lock**, since it already
implements a battle-tested cross-process claim (OS byte-range lock on a
per-ticket file, liveness proven by `_probe_dead`'s non-blocking re-lock
attempt) instead of writing a new heartbeat primitive from scratch.

Rejected: `host_resource_lease` proves liveness by holding an OS lock open
for the duration of ONE resource-holding subprocess (e.g. the F0 test-suite
run it was built for) — the lock's holder and the process are the same
Python `with` block. The campaign loop has no such process: step 0 through
step 4 are a *series* of independent `uv run` subprocess calls issued across
a Claude Code session's tool calls, none of which stays alive for the
campaign's duration. There is nothing for an OS-level lock to attach to that
would still be held (or reliably released) hours later at the next `touch`.
A heartbeat — record who holds it and when they last touched it, reclaim
past a staleness threshold — is the correct primitive for "liveness of a
*logical* session across many short-lived processes", which is what this
guard actually needs. `host_resource_lease`'s namespace-hardening machinery
(`_safe_dir`, `_windows_private`, etc.) was also built for a systemwide
shared temp root serving *sibling worktrees of any project* — overkill for a
lock that only ever needs to live inside one already-isolated campaign
worktree, itself already under a private, git-ignored `.worktrees/` tree.

## Confidence

High that the heartbeat design closes the named gap (a second live session
is rejected; a dead one's lock is reclaimed, bounded by
`DEFAULT_STALE_AFTER_SECONDS`) without inventing new session-liveness
infrastructure beyond the campaign path, per the card's explicit scope
limit. Residual, documented (not solved) gap: the branch-identity check's
prefix match cannot fully disambiguate adjacent hyphenated campaign slugs —
accepted per the card's own "cheap assertion" framing.
