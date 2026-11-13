# F7b — Event-log follow-up commit (out-of-band F7 only)

> **Not needed for a normal worktree iterate.** Since
> iterate-2026-05-29-events-jsonl-worktree-commit the F5b event is committed
> by **F6** inside the worktree and ships in the PR, so there is no tracked-dirty
> main-tree append to seal. F7b pairs only with an **out-of-band F7**
> (`record_event.py`) call that writes the **main tree's** log directly —
> replay, non-worktree phases, CI automation.

When `shipwright_events.jsonl` is **tracked** in the project (rare —
shipwright dev repo, and any downstream that chooses to track it via
`!/shipwright_events.jsonl` in `.gitignore`), an out-of-band F7 append leaves a
tracked-dirty file. Run this immediately after that `record_event.py` to
seal the append in a small follow-up commit so it survives the next
`git reset --hard` / `git stash` / rebase. The tool is idempotent:
gitignored / clean / untracked / dry-run all return cleanly without
producing a commit, so it is safe to run unconditionally.

```bash
uv run "{shared_root}/scripts/tools/commit_event_followup.py" \
  --project-root "{project_root}" \
  --run-id "{run_id}" \
  --event-id "{event_id from F7 stdout}" \
  --co-author "Claude <noreply@anthropic.com>"
```

The tool prints a JSON status to stdout: `committed` / `partial` / `clean` /
`ignored` / `untracked` / `skipped` / `dry_run`. The `committed` and `partial` statuses carry
the new commit SHA. Only those two produce a new commit on the branch; all other statuses
are noops. `partial` means the commit was made but your event was NOT sealed (drops layout, see below).

> **Drops layout.** The tool also seals every UNTRACKED drop written from the main tree
> (`.shipwright/events/drops/_main--*` and any file whose worktree id is the main git dir's): it lists them
> with `git ls-files --others`, validates each is whole, and commits exactly those paths
> (`chore(events): seal event drops for <run_id>`). The `committed` status then carries a `sealed`
> list. A non-empty index (`staged_changes`) skips instead. A torn file stays in the working copy and is named in
> `left_behind` while the whole drops are sealed; if the event you just wrote sits in that torn file the status is
> `partial` (a commit WAS made for the whole drops, but your event is NOT sealed: repair the file). Only when EVERY pending
> drop is torn is nothing sealed (`invalid_drop`). A torn file keeps catching new events of its key until it is
> repaired, so `left_behind` needs a manual fix.

> **Why this exists.** SKILL.md historically documented F7 as
> "writes only to a gitignored event log" — incorrect for
> self-tracking repos. On 2026-05-22 a `git reset --hard origin/main`
> after a security rebase loop silently wiped 9 tracked-dirty post-F7
> events from the shipwright dev repo's event log (the recovery
> commit landed as PR #70). F7b closes that hole structurally.
