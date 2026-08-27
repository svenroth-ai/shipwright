# Campaign Worktree

`sub-iterate-runner.md` "works on the project directly (no worktree)" — meaning
it never calls `setup_iterate_worktree.py` itself, but that phrase only
describes the runner correctly when it is spawned INSIDE an already-isolated
directory. Nothing previously gave the campaign one, so a session that started
at the bare main repository root simply stayed there, and every runner it
spawned branched, built and committed straight in `main`'s own checkout — two
production campaigns hit exactly this. This document is the fix: ONE worktree
per **campaign slug**, shared by the orchestrator and every `sub-iterate-runner`
it spawns for the whole campaign, set up before anything else and re-verified
immediately before every spawn.

## Setup (Autonomous Campaign Loop step 0 — unconditional, before anything else)

Keyed to the **campaign slug**, not to whichever session is driving the loop
right now, so a resumed campaign always re-enters the same isolated directory
instead of a fresh session rooted in main:

```bash
main_root=$(dirname "$(git rev-parse --path-format=absolute --git-common-dir)")
campaign_wt="$main_root/.worktrees/campaign-{slug}"
orchestrator_run_id="iterate-{today, YYYY-MM-DD}-campaign-{slug}"  # THIS session's own id — never a sub-iterate's run_id
if [ -d "$campaign_wt" ]; then
  cd "$campaign_wt"   # RESUME — a prior session already created it
else
  result=$(uv run "{shared_root}/scripts/tools/setup_iterate_worktree.py" \
    --project-root "$main_root" --slug "campaign-{slug}" --run-id "$orchestrator_run_id")
  cd "$(python3 -c 'import json,sys; print(json.load(sys.stdin)["project_root"])' <<< "$result")"
fi
# No-op on the resume path above (already-inside-a-worktree branch) — ensures
# the run pointer + main-tree snapshot exist for THIS session too, never
# re-creates the worktree the fresh-create branch just made:
uv run "{shared_root}/scripts/tools/setup_iterate_worktree.py" \
  --project-root . --slug "campaign-{slug}" --run-id "$orchestrator_run_id"
```

`{project_root}` for the rest of the campaign session — the orchestrator's own
steps AND every `project_root` handed to a `sub-iterate-runner` spawn — is this
worktree. Never `.` resolved against wherever the session happened to start,
and never the main repository root.

### Session-liveness lock (same step 0 — immediately after the worktree resolves)

The worktree above is *shared* by every session that ever drives this slug —
two operators, or one operator resuming a session it believed had died, both
reach the same `campaign_wt` and can spawn a `sub-iterate-runner` whose
`git checkout -b` races the other's in the one shared directory.
`autonomous_loop.py`'s `file_lock` only serializes `loop_state.json` writes and
does not cover this. Verify identity FIRST — a mis-substituted `{project_root}`
must never acquire a lock that then reports success for the wrong directory —
then claim exclusive ownership before step 1:

```bash
uv run "{shared_root}/scripts/checks/check_worktree_location.py" \
  --project-root "{project_root}" --campaign-slug "{slug}" && \
uv run "{shared_root}/scripts/checks/check_campaign_session_lock.py" acquire \
  --campaign-worktree "{project_root}" --session-id "$SHIPWRIGHT_SESSION_ID"
```

Joined with `&&` deliberately — a shell snippet in a runtime prompt is code,
not documentation, and two bare lines would run `acquire` unconditionally
even after `check_worktree_location.py` exits non-zero, acquiring a lock
against a mis-substituted `{project_root}` (main root, a sibling campaign)
before the identity failure is ever seen.

Non-zero exit from EITHER = **abort campaign startup** — do not proceed to
step 1. The lock error names the session currently holding it, how long ago
and at what wall-clock time it last touched it; if `$SHIPWRIGHT_SESSION_ID` is
unset or empty instead, the error says so explicitly — re-export it or
re-run the SessionStart hook. Either way: tell the operator, do not
self-repair-and-retry (nothing has started yet, so there is nothing to
STRICT-STOP into step 4 for). A SAME `SHIPWRIGHT_SESSION_ID` re-running the
lock command always succeeds (the legitimate resume path — see the caveat on
that assumption in `lib/campaign_session_lock.py`'s module docstring). If
instead an operator is certain the prior session is gone and does not want to
wait out the staleness window, the error also names the state file
(`{campaign_wt}/.shipwright/campaign_session.lock.json`) to delete for an
immediate reclaim — **only after confirming no `sub-iterate-runner` Task is
still running against this worktree**: deleting it while that session's
runner is still live re-opens the exact race this lock exists to prevent, and
the deleting operator has no way to verify liveness other than that
confirmation (there is no OS process to check). See
`lib/campaign_session_lock.py` for the liveness model: there is no single OS
process to attach an OS-level lock to (the loop is driven by a series of
independent `uv run` subprocess calls, not one long-lived process), so a
DIFFERENT session may only reclaim the lock once it has gone stale —
presumed abandoned, never blocked forever.

**The release step.** Nothing about the acquire/touch pair ever removes the
lock, so a campaign that finishes cleanly leaves it in place — the routine
case where an operator's Claude Code session died or ran out of context and
they resume with a *new* `SHIPWRIGHT_SESSION_ID` would otherwise be refused
for up to `stale_after_seconds` by its own already-completed prior run.
`campaign-mode.md` step 4 (Finalize) releases it as its first action, once,
so a completed campaign never blocks its own restart.

**The touch coverage gap.** A touch only resets the staleness deadline at the
instant it runs — it does not cover the wait that follows. `campaign-mode.md`
loop step 3a `touch`es this lock at the top of every iteration, and step 3g
touches it again immediately before `gh pr checks --watch`, but **two**
windows remain genuinely unbounded and untouched while they run: (1) the
`sub-iterate-runner` Task itself (3c spawn through 3d's wait on the terminal
DONE marker: build + reviews + F0–F6 + push) — the loop's longest block, and
(2) `gh pr checks --watch` plus the merge-status poll after it, which the 3g
touch only precedes rather than covers. A sub-iterate — or a slow CI run —
that takes longer than `DEFAULT_STALE_AFTER_SECONDS` can go stale and be
reclaimed by a second session while the first is still working inside the
same shared worktree; that constant has no measured p95 behind it (see its
docstring). Closing this fully means the runner itself heartbeats the lock
(it is the process actually occupying the worktree) — documented, not
solved here; this section names the gap rather than overclaiming it is
covered so the next reader does not have to re-derive it.

**A worktree recreate silently drops the lock.** The state file lives
*inside* the worktree it protects (`{campaign_wt}/.shipwright/`), so
repairing the worktree (`git worktree remove` + re-create — the prescribed
response to a `sub-iterate-runner` returning `reason_code: "not_isolated"`,
or any `git clean -xfd` inside it) deletes the lock along with everything
else. Any other session can acquire immediately after, and the legitimate
owner's own next touch then fails LOCK-LOST, stopping the campaign it just
repaired. Re-`acquire` right after any worktree recreate to close this.

## Spawn guard (Autonomous Campaign Loop step 3c — before every spawn)

A long-running session can drift (an earlier `cd`, a resumed session starting
at the repo root); re-verify immediately before handing a directory to a
runner subagent, rather than trusting step 0 stayed true:

```bash
uv run "{shared_root}/scripts/checks/check_worktree_location.py" \
  --project-root "{project_root}" --campaign-slug "{slug}"
```

Non-zero exit = STRICT-STOP the whole loop, same as campaign-mode.md step 3c
says — go to step 4 (Finalize), do NOT spawn the runner into an unverified
directory, and do NOT self-repair-and-retry (matching every other
STRICT-STOP in the loop: 3f, 3f-bis, 3g).

This is deliberately NOT the fuller F0/F11 leak-guard
(`check_iterate_isolation.py`): that one also diffs the main tree against a
Step-1 snapshot keyed by `run_id`. A campaign sub-iterate never has one — it
mints its own `run_id` (loop step 3b) but never calls
`setup_iterate_worktree.py` for it — and the diff would also misreport
campaign-mode step 3h's own deliberate main-tree write (the live-board
`status.json`) as a leak. `check_worktree_location.py`
(`lib.worktree_location.worktree_location_error`) checks location — is
`{project_root}` a worktree under `<main_root>/.worktrees/`? — and, via
`--campaign-slug`, identity: is its worktree directory named
`campaign-{slug}` EXACTLY, not just some still-valid worktree? No snapshot,
no `run_id` either way. Checked against the directory name, not the
checked-out branch — the directory is fixed at creation and never changes
for the campaign's lifetime, while the branch inside it moves per
sub-iterate; see `lib/worktree_location.py` for why a branch-prefix check was
tried and rejected (it cannot tell two campaigns whose slugs are themselves a
hyphenated extension of one another, e.g. `req3` vs `req3-04`, from a slug
plus a sub-iterate suffix).

## Defense in depth: the runner's own check

`sub-iterate-runner.md` Step 1.0 runs the same `check_worktree_location.py`
command (with `--campaign-slug "{campaign_slug}"`, passed as its own brief
parameter — the orchestrator's SAME `{slug}` it already has in scope at step
3c, not re-derived from `{campaign_path}`'s basename inside the runner; one
derivation, one shape, nothing for the two guards to disagree about) against
its own `{project_root}` before touching git, and refuses
(`status:"failed"`, `reason_code: "not_isolated"`) if it fails. A freshly
spawned subagent's shell does not reliably inherit the orchestrator's `cd`, so
this is not redundant with the step 3c guard above — it is the last line of
defense if a bad `project_root` ever reaches a spawn anyway. Every git command
inside `sub-iterate-runner.md` is `git -C "{project_root}"` for the same
reason: the shared F0–F6 finalization prose it follows (`F6.md`, etc.) is
written assuming cwd already IS the worktree, which is only true for a
standalone iterate unless the runner makes it true for itself too. The
handful of relative-path `git add`/`git commit` calls inside `F6.md`/`F4.md`
that were deliberately NOT rewritten (see Out of Scope) stay safe because a
Bash-tool session's cwd persists across every later command IN THAT SAME
session — the same guarantee Step 1.0's single `cd` relies on for the rest
of the runner's own lifecycle, not an untested assumption.
