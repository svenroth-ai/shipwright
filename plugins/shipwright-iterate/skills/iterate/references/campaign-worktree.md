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
`sub-iterate-runner` Task(s) themselves (3c's multi-spawn through the
implicit wave-return once every Task in that message has returned — R5a
retired the terminal DONE marker for `kind == "sub_iterate"`, see
`campaign-mode.md` 3d — covering build + reviews + F0–F6 + push per unit) —
the loop's longest block, and
(2) `gh pr checks --watch` plus the merge-status poll after it, which the 3g
touch only precedes rather than covers. A sub-iterate — or a slow CI run —
that takes longer than `DEFAULT_STALE_AFTER_SECONDS` (7200s / 2h — a round,
generous guess with no measured p95 behind it; see the constant's own
docstring in `lib/campaign_session_lock.py`) can go stale and be reclaimed by
a second session while the first is still working inside the same shared
worktree.

**Narrowed for window (1) — the runner itself heartbeats the lock (R2).**
The `sub-iterate-runner` subagent — the process actually occupying the
worktree for the whole of window (1) — calls `check_campaign_session_lock.py
touch` at its own step boundaries (Step 1 after branch setup, before Step 4
Finalization, before Step 5 Push), using the `session_id` it receives in its
own brief (the ORCHESTRATOR's `$SHIPWRIGHT_SESSION_ID` — the lock's
`touch()` validates `existing["session_id"] == session_id` against the
owning session, never a subagent's own identity, so passing anything else
makes every touch raise `CampaignLockError`). Under the wave model (the
orchestrator itself is blocked for the whole of window (1)), **this runner
touch is the SOLE coverage for that window, not merely additional
coverage** — nothing else touches the lock while the Task is running.

**Honest limit (external plan review, OpenAI, high — this is a per-STEP
touch, not a continuous heartbeat).** The three step boundaries above turn
window (1) into three SHORTER sub-windows (Step 1→Step 4, i.e. Build +
reviews; Step 4→Step 5, i.e. Finalization), not zero exposure — a single one
of those sub-windows (e.g. a very long F0 full-suite run inside Build) can
itself still exceed `DEFAULT_STALE_AFTER_SECONDS` and go untouched for its
whole duration. R2 scopes to these three boundaries; touching more finely
(e.g. between individual F-phases) is a future refinement, named here rather
than overclaimed as already closed.

A failed touch is **warn-and-continue, never fatal to the runner's own
build** — this is the sub-iterate spec's OWN explicit, deliberate design
(not an oversight this doc papers over): a touch failure (lock released
early, reclaimed past staleness, or the worktree recreated) says nothing
about whether the runner's current build is healthy, and the orchestrator's
own step-3a/3g touches remain the authoritative lock-lost detector — see the
spec's own "warn-and-continue, never fatal" rationale. (External plan
review, OpenAI, high, proposed treating an ownership-loss touch failure as
fatal instead; rejected — reversing this rule is out of scope for R2, which
implements the spec's stated design rather than relitigating it.) Window (2)
(`gh pr checks --watch` + the merge-status poll) remains open — that runs in
the orchestrator's own process, after the runner Task has already returned,
so it is out of scope for a runner-side heartbeat; documented, not solved
here.

The runner ALSO heartbeats its own PER-UNIT lease at the same step
boundaries (`check_unit_lease.py touch`, see "Per-unit worktree path" below)
— a separate mechanism, on a separate row of `loop_state.json`, guarded by
the existing `loop.lock` rather than this campaign-wide session lock. The
two are independent: a campaign session-lock failure means a second SESSION
may now be driving the campaign; a lease-touch failure means only THIS
UNIT's own liveness signal went stale, and is even more strictly
warn-and-continue (no fencing-token validation applies to it at all until R4
lands — see "Per-unit worktree path" below for why).

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

## Per-unit worktree path (R2 built it; R5a wires it live)

R2 built the naming, guard-mode identity, lease mechanism, and worktree
wrapper a per-unit worktree needs; R5a ("the flip") wires it into the live
loop — `campaign-mode.md` step 3c now invokes `setup_unit_worktree.py` for
every unit in a wave, each into its own `.worktrees/campaign-{slug}--{id}`
sibling, before any concurrent `Task` spawn. Every OTHER `{project_root}` in
this document still means the ONE shared campaign worktree — the per-unit
path exists only for the duration of one unit's own build, spawned as that
unit's own `project_root` (never the shared one) in the runner's brief.

**Path form:** `.worktrees/campaign-{slug}--{unit_id}` for attempt 0, and
`.worktrees/campaign-{slug}--{unit_id}-a{attempt}` for a retry attempt >= 1
(R4 mints attempts). `lib.campaign_unit_worktree.composite_worktree_name`
is the single place that constructs this string, reused by every call site
(the wrapper below, a future R4 reconcile/cleanup) so none of them can drift
apart. `--` is the reserved separator between the two components —
`lib.campaign_graph.id_charset_ok` (R1) already rejects a literal `--`
inside either a campaign slug or a unit id, so a malformed value can never
forge a second separator and collide two different `(slug, unit_id)` pairs
onto the same composite string.

**Guard-mode, not "either form" OR.** `check_worktree_location.py`'s
existing `--campaign-slug` parameter accepts this composite value
(`"{slug}--{unit_id}"`) with **zero code change** to `lib.worktree_location`
itself — that guard only ever compares the worktree DIRECTORY's exact
basename against `campaign-{expected_campaign_slug}`, so passing the
composite string is call-site wiring, not new guard logic. It is a MODE, not
an OR: the orchestrator's own step-3c check (above) validates only the
shared campaign path; the runner's own Step 1.0 check, once R5a flips it,
validates only its own per-unit path. An OR would let a runner legally sit
in the shared campaign worktree even after the flip — exactly the race
per-unit worktrees exist to remove.

**Worktree lifecycle wrapper:** `setup_unit_worktree.py` reuses
`setup_iterate_worktree.py`'s fresh-fetch / gitignore / cleanup behavior
UNCHANGED, via that script's own `slug` parameter — it does not
re-implement any of it. Its own job is narrow: build the composite identity
from validated inputs, check the total resolved path length, then delegate.

**Total path-length bound (Windows finding).** A unit id's length alone is
bounded (64 chars, R1's `_ID_CHARSET_RE`), but the TOTAL resolved path is
not — a real ~35-char campaign slug, plus `campaign-`, plus a 64-char unit
id, plus an `-a{n}` attempt suffix, under this repo's own nested
`.worktrees/` structure, can reach Windows' `MAX_PATH` (260) on the stated
primary dev platform. `setup_unit_worktree.py` computes the full path length
and fails loudly (exit 5, naming the campaign slug and unit id) BEFORE
calling `git worktree add`, rather than letting git fail mid-checkout with
an opaque error.

**Security hardening.** Every function in `lib.campaign_unit_worktree`
RECOMPUTES the expected worktree path from validated `(slug, unit_id,
attempt)` — a destructive caller (a future R4 cleanup) must never trust a
path string read back from `loop_state.json` instead of recomputing it here
— and refuses a resolved path landing outside `<main_root>/.worktrees/`.

**Per-unit lease.** `lib.unit_lease` / `check_unit_lease.py touch` maintain
`attempt`, `attempt_id`, `lease_touched_at`, `lease_expires_at`, `worktree`,
and `branch` on the unit's OWN row in `loop_state.json` — guarded by the
SAME `loop.lock` / `file_lock` `autonomous_loop.py` already serializes every
other `loop_state.json` write through, deliberately not a second state
file. It is a **field-creating upsert**: this campaign's own DAG makes R2
independent of R1, so a row is not guaranteed to already carry these fields,
and the first touch for a unit creates them. **No fencing-token validation
applies to it** — R4 adds that for every OTHER claim mutation; this touch is
the explicit, documented exception until R4 lands. Like the campaign session
lock's own touch, a failed lease touch is **warn-and-continue, never
fatal** to the runner's own build.

Two non-fencing refinements (external plan review): a touch whose caller
`attempt` is LOWER than the row's already-recorded `attempt` still succeeds
(no rejection — that stays R4's job) but is marked
`stale_attempt_conflict: true` in its own return value / CLI warning, so a
caller can distinguish "touching a row no longer mine" from a normal
heartbeat without this being a fencing check; and an optional
`--campaign-worktree` flag on `check_unit_lease.py touch` cross-checks that
`--state` actually resolves under `{campaign_worktree}/.shipwright/` —
catching the two brief parameters having drifted apart from each other.

**Single-writer invariant, unaffected by the flip.** Campaigns keep using
this narrow location guard rather than the full `check_iterate_isolation.py`
leak-guard even once a per-unit worktree carries its own run-pointer /
main-tree snapshot (`setup_unit_worktree.py` writes both, via the
`setup_iterate_worktree.setup()` it delegates to) — that fuller guard's
main-tree diff would still misreport campaign-mode step 3h's own deliberate
`status.json` write as a leak (see "Spawn guard" above). Campaign-level
`status.json` regeneration happens ONLY in the campaign worktree — the
orchestrator itself, or the churn resolver — never in a per-unit worktree; a
per-unit worktree's runner writes only its own per-unit iterate artifacts.
Enforced by the same isolation guard: a per-unit worktree's runner never
holds a `{project_root}` that resolves to the campaign worktree, so it has
no path through which to reach `status.json` in the first place.

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
