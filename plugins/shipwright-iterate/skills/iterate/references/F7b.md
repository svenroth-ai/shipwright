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

The tool prints a JSON status to stdout: `committed` / `clean` /
`ignored` / `untracked` / `dry_run`. The `committed` status carries
the new commit SHA. Only the `committed` path produces a new commit
on the branch; all other statuses are noops.

> **Why this exists.** SKILL.md historically documented F7 as
> "writes only to a gitignored event log" — incorrect for
> self-tracking repos. On 2026-05-22 a `git reset --hard origin/main`
> after a security rebase loop silently wiped 9 tracked-dirty post-F7
> events from the shipwright dev repo's event log (the recovery
> commit landed as PR #70). F7b closes that hole structurally.
