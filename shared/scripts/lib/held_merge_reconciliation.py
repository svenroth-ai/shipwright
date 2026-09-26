"""Held-merge reconciliation for campaign-mode.md step 4 (Finalize)
(campaign-dag-scheduler R5b rounds 3-4 and 6, Tier-3 review; round 7:
"add executable integration coverage for ... held-merge reconciliation").

R5b smoke-test conflict probe (throwaway): deliberately touches the same
docstring line as the sibling unit's change to exercise the rebase cascade.

Two `reason_code`s can leave a unit `held` while its PR is actually merged,
and neither self-heals without this pass:

- `drain_timeout` — `campaign_drain.py`'s own bounded drain force-
  transitioned `merging -> held`, but the unit's OWN in-flight `gh pr merge`
  may complete genuinely AFTER that forced transition (a forced transition
  changes the RECORD, never the WORKER — no cancellation primitive exists
  for an already-spawned Task).
- `merge_confirmation_timeout` — step 3g's own poll already confirmed
  `state == "MERGED"` before demoting to `held`; only `mergeCommit.oid`
  never arrived within its bound. This row is not "maybe merged" like the
  one above, it IS merged.

Both share the same remedy — re-check the unit's PR against GitHub's own
state and correct the record if it actually landed — so one pass covers
both `reason_code`s. Each unit gets its own short, bounded grace window
(mirroring step 3g's own `mergeCommit` confirmation wait): a `gh` query
failure retries within that window rather than being treated as proof the
PR is still open, and exhausting the window leaves the row exactly as
recorded — a safe, terminal `held` state, reconcilable on a LATER run —
rather than turning this best-effort correction into a new STRICT-STOP
surface.

**This narrows the race, it does not close it.** The truly unbounded part
of a stuck worker is `gh pr checks --watch` waiting on slow/hung CI —
nothing bounds how long THAT can run, so no fixed reconciliation window can
guarantee catching every case; a worker whose CI wait outlives this grace
window too can still merge genuinely after finalize. Closing this fully
would require a Task-cancellation primitive this framework does not have
(see `lib.campaign_drain`'s own module docstring) — this bounded retry is
the best available mitigation, not a claim of closure.

`loop_claim.py mark`'s own `--status merged` path re-fetches `origin` and
verifies the SHA's ancestry itself (never trusts a hand-derived value
blindly, since this is the one operator-override path), so no separate
ancestry check is needed here. A unit whose PR is genuinely still unmerged
(the common case) or whose `gh` query fails throughout the window is left
exactly as the drain recorded it — this pass only ever CORRECTS a stale
`held` into `merged`, never the reverse.

**Also corrects the local campaign_progress.json board (round 12, Tier-3
review).** Step 3h maps a `merge_confirmation_timeout` unit to `failed` on
that board WHILE it is still `held` — before this pass ever runs, since 3h
fires per-wave and this pass only runs once, at Finalize, after every wave
completes. Left alone, that board would show `failed` forever for a unit
`loop_state.json` now correctly records as `merged`, since 3h never
revisits an already-cleared unit. `update_progress_fn` corrects it right
after `mark_merged_fn` succeeds — best-effort, matching 3h's own convention
that this board is a "LOCAL-BOARD CONVENIENCE only" (campaign-mode.md,
step 3h) whose failures never block anything.

**Every subprocess call in this module is timeout-bounded (round 12 for
`gh`, round 13 for `loop_claim.py mark` and `campaign_progress.py
update-status`, both Tier-3 review, blocking).** A hang in any one of them
would otherwise block step 4's finalize — and the session-lock release
that follows it — indefinitely, which is exactly the failure mode this
pass's own bounded-window design exists to rule out. A timed-out call is
just another failed/best-effort operation, never an uncaught exception.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable

#: `reason_code`s a `held` unit may carry that this pass is licensed to
#: correct — anything else (an operator override, a genuine rebase
#: conflict, ...) is left untouched.
RECONCILABLE_REASON_CODES = ("drain_timeout", "merge_confirmation_timeout")

#: Per-unit bounded grace window (round 6) — same shape as 3g's own
#: `mergeCommit` confirmation wait, not a single-instant check.
DEFAULT_RECONCILE_SECONDS = 60.0
DEFAULT_POLL_INTERVAL_SECONDS = 5.0

#: Per-call bound on the `gh` subprocess itself (Tier-3 review, R5b round 12,
#: blocking): `subprocess.run` with no `timeout=` can hang indefinitely on a
#: wedged `gh` process (a stuck network call, an interactive auth prompt with
#: no TTY to answer it), which defeats `DEFAULT_RECONCILE_SECONDS` entirely --
#: the outer deadline is only checked BETWEEN calls, never while one is still
#: running. Well under the poll interval so a single hang still leaves room
#: to retry within the outer window rather than consuming it in one call.
GH_QUERY_TIMEOUT_SECONDS = 20.0

#: Per-call bound on the mark/board-update subprocess calls (Tier-3 review,
#: R5b round 13, blocking): the same hang risk `GH_QUERY_TIMEOUT_SECONDS`
#: above already covers for `gh` -- a stuck `uv` launch or a wedged
#: `loop_claim.py mark`/`campaign_progress.py update-status` had no timeout
#: at all, so either could hang step 4's finalize (and the session-lock
#: release that follows it) indefinitely, despite this pass documenting
#: itself as bounded.
SUBPROCESS_TIMEOUT_SECONDS = 30.0

#: (branch, cwd) -> {"state": ..., "mergeCommit": {"oid": ...}} | None on a `gh` failure.
GhQueryFn = Callable[[str, str], "dict | None"]
#: (unit_id, merged_sha) -> success.
MarkMergedFn = Callable[[str, str], bool]
#: (unit_id, merged_sha, branch) -> success. Best-effort only -- see `reconcile`.
UpdateProgressFn = Callable[[str, str, str], bool]


def find_reconcilable_held(state: dict) -> list[dict]:
    """The `held` units whose `reason_code` this pass is licensed to
    correct — computed once, up front, exactly like the bash block's own
    single `jq` snapshot (later units marked `merged` mid-pass never widen
    this list)."""
    return [
        u for u in state.get("units", [])
        if u.get("status") == "held" and u.get("reason_code") in RECONCILABLE_REASON_CODES
    ]


def poll_for_merged_sha(
    gh_query_fn: GhQueryFn, branch: str, cwd: str, *,
    deadline_seconds: float, poll_interval_seconds: float, sleep_fn, time_fn,
) -> str | None:
    """A `gh` query failure retries within the same bounded window (never
    treated as proof the PR is still open); a `MERGED` state with an empty
    `mergeCommit.oid` also keeps polling (the merge event and the SHA
    becoming visible are not atomic). Returns the merged SHA, or ``None``
    once the window elapses first."""
    deadline = time_fn() + deadline_seconds
    while time_fn() < deadline:
        result = gh_query_fn(branch, cwd)
        if result is not None and result.get("state") == "MERGED":
            # `.get("mergeCommit", {})` only substitutes the default when the
            # KEY is absent -- GitHub returns the key with an explicit JSON
            # `null` while MERGED but the SHA has not become visible yet
            # (the exact race this docstring says to keep polling through),
            # and `None.get(...)` raises (Tier-3 review, R5b round 10,
            # blocking). Normalize the value itself, not just the key.
            merge_commit = result.get("mergeCommit") or {}
            sha = merge_commit.get("oid") or None
            if sha:
                return sha
        sleep_fn(poll_interval_seconds)
    return None


def reconcile(
    state: dict, *, project_root: str, gh_query_fn: GhQueryFn, mark_merged_fn: MarkMergedFn,
    update_progress_fn: UpdateProgressFn | None = None,
    deadline_seconds: float = DEFAULT_RECONCILE_SECONDS,
    poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS,
    sleep_fn=time.sleep, time_fn=time.time,
) -> list[dict]:
    """Returns the `{id, merged_sha}` rows this pass corrected. Never
    mutates `state` itself -- correcting the record is `mark_merged_fn`'s
    job (the real CLI shells out to `loop_claim.py mark`, which re-verifies
    the SHA's ancestry before accepting it).

    `update_progress_fn`, when given, is called after a successful
    `mark_merged_fn` to also correct the LOCAL-BOARD campaign_progress.json
    entry (Tier-3 review, R5b round 12, blocking): step 3h maps a `held`/
    `merge_confirmation_timeout` unit to `failed` on that board WHILE the
    unit is still `held`, which is BEFORE this reconciliation pass ever
    runs (3h fires per-wave; this pass only runs once, at Finalize, after
    every wave). Left uncorrected, the board would show `failed` forever
    for a unit `loop_state.json` now correctly records as `merged` -- 3h
    never revisits an already-cleared unit to fix it. Best-effort only,
    matching 3h's own established convention (references/campaign-mode.md,
    step 3h: "LOCAL-BOARD CONVENIENCE only ... skipping it only affects the
    live orchestrator view") -- its return value does not gate whether this
    unit counts as `corrected` below, since `loop_state.json` is already the
    durable record and correcting it is this function's actual job."""
    corrected = []
    for unit in find_reconcilable_held(state):
        unit_id = unit["id"]
        branch = unit.get("branch")
        cwd = unit.get("worktree")
        if not cwd or not Path(cwd).is_dir():
            cwd = project_root
        merged_sha = poll_for_merged_sha(
            gh_query_fn, branch, cwd,
            deadline_seconds=deadline_seconds, poll_interval_seconds=poll_interval_seconds,
            sleep_fn=sleep_fn, time_fn=time_fn,
        )
        if merged_sha is None:
            continue  # exhausted the window -- leave the row exactly as recorded
        if mark_merged_fn(unit_id, merged_sha):
            corrected.append({"id": unit_id, "merged_sha": merged_sha})
            if update_progress_fn is not None:
                update_progress_fn(unit_id, merged_sha, branch)
    return corrected


def _real_gh_query(branch: str, cwd: str) -> dict | None:
    try:
        proc = subprocess.run(
            ["gh", "pr", "view", branch, "--json", "state,mergeCommit"],
            cwd=cwd, capture_output=True, text=True, check=True,
            timeout=GH_QUERY_TIMEOUT_SECONDS,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
        return None
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return None


def _real_mark_merged(unit_id: str, merged_sha: str, *, state_path: Path, project_root: str, shared_root: str) -> bool:
    try:
        result = subprocess.run([
            "uv", "run", str(Path(shared_root) / "scripts" / "lib" / "loop_claim.py"), "mark",
            "--state", str(state_path), "--unit", unit_id, "--status", "merged",
            "--force", "--confirm-no-task-running",
            "--campaign-worktree", project_root, "--merged-commit", merged_sha,
            "--reason", "held-merge reconciliation: GitHub reports this PR as merged although the unit was recorded held",
            "--operator", "campaign-mode:4-reconcile", "--reason-code", "held_merge_reconciled",
        ], timeout=SUBPROCESS_TIMEOUT_SECONDS)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def _real_update_progress(
    unit_id: str, merged_sha: str, branch: str, *, campaign_dir: str, plugin_root: str,
) -> bool:
    """Best-effort local-board correction (see `reconcile`'s own docstring).
    A failure here is intentionally not surfaced as an error -- the same
    convention step 3h's own call already established."""
    try:
        result = subprocess.run([
            "uv", "run", str(Path(plugin_root) / "scripts" / "tools" / "campaign_progress.py"), "update-status",
            "--campaign-dir", campaign_dir, "--sub-iterate-id", unit_id,
            "--status", "complete", "--commit", merged_sha, "--branch", branch,
        ], timeout=SUBPROCESS_TIMEOUT_SECONDS)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--shared-root", required=True)
    parser.add_argument("--plugin-root", required=True)
    parser.add_argument("--campaign-dir", required=True)
    parser.add_argument("--deadline-seconds", type=float, default=DEFAULT_RECONCILE_SECONDS)
    parser.add_argument("--poll-interval-seconds", type=float, default=DEFAULT_POLL_INTERVAL_SECONDS)
    args = parser.parse_args(argv)

    state = json.loads(args.state.read_text(encoding="utf-8"))

    def mark_merged(unit_id: str, merged_sha: str) -> bool:
        return _real_mark_merged(unit_id, merged_sha, state_path=args.state,
                                  project_root=args.project_root, shared_root=args.shared_root)

    def update_progress(unit_id: str, merged_sha: str, branch: str) -> bool:
        return _real_update_progress(unit_id, merged_sha, branch,
                                      campaign_dir=args.campaign_dir, plugin_root=args.plugin_root)

    corrected = reconcile(
        state, project_root=args.project_root, gh_query_fn=_real_gh_query, mark_merged_fn=mark_merged,
        update_progress_fn=update_progress,
        deadline_seconds=args.deadline_seconds, poll_interval_seconds=args.poll_interval_seconds,
    )
    for row in corrected:
        print(f"reconciled {row['id']} -> merged ({row['merged_sha']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
