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

## Spawn guard (Autonomous Campaign Loop step 3c — before every spawn)

A long-running session can drift (an earlier `cd`, a resumed session starting
at the repo root); re-verify immediately before handing a directory to a
runner subagent, rather than trusting step 0 stayed true:

```bash
uv run "{shared_root}/scripts/checks/check_worktree_location.py" \
  --project-root "{project_root}"
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
(`lib.worktree_location.worktree_location_error`) checks only location: is
`{project_root}` a worktree under `<main_root>/.worktrees/`, yes or no — no
snapshot, no `run_id`.

## Defense in depth: the runner's own check

`sub-iterate-runner.md` Step 1.0 runs the same `check_worktree_location.py`
command against its own `{project_root}` before touching git, and refuses
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

## Known limitations (doubt-review round, not fixed here)

- **No cross-session lock on the shared campaign worktree.** Two operators
  (or one operator resuming a session they believed had died) can both drive
  `--campaign <slug> --autonomous` against the same slug at once; each
  reaches the same `campaign_wt` and can spawn a `sub-iterate-runner` whose
  `git checkout -b` races the other's in the one shared directory. Nothing
  in this fix — or in `autonomous_loop.py`'s `file_lock`, which only
  serializes `loop_state.json` writes — prevents it. This is a pre-existing
  class of risk (a standalone iterate's own resume path has never had a
  session lock either) that campaign mode now shares rather than a new one
  this fix invented; closing it needs a session-liveness lock, deliberately
  left as a follow-up rather than folded into a same-day incident fix.
- **The guard proves location, not identity.** `worktree_location_error`
  answers "is `{project_root}` a worktree under `.worktrees/`", not "is it
  THIS campaign's worktree" — a mis-threaded `project_root` pointing at a
  different, still-valid worktree (a stale prior campaign, a sibling
  campaign) would pass both checks unchanged. Deliberately out of scope: the
  reported incident was "landed on `main`", which location-only closes
  completely; adding a branch-identity check is a reasonable follow-up, not
  a requirement for closing this incident.
