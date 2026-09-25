"""Held-merge reconciliation for campaign-mode.md step 4 (Finalize)
(campaign-dag-scheduler R5b rounds 3-4 and 6, Tier-3 review; round 7:
"add executable integration coverage for ... held-merge reconciliation").

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

#: (branch, cwd) -> {"state": ..., "mergeCommit": {"oid": ...}} | None on a `gh` failure.
GhQueryFn = Callable[[str, str], "dict | None"]
#: (unit_id, merged_sha) -> success.
MarkMergedFn = Callable[[str, str], bool]


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
            sha = result.get("mergeCommit", {}).get("oid") or None
            if sha:
                return sha
        sleep_fn(poll_interval_seconds)
    return None


def reconcile(
    state: dict, *, project_root: str, gh_query_fn: GhQueryFn, mark_merged_fn: MarkMergedFn,
    deadline_seconds: float = DEFAULT_RECONCILE_SECONDS,
    poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS,
    sleep_fn=time.sleep, time_fn=time.time,
) -> list[dict]:
    """Returns the `{id, merged_sha}` rows this pass corrected. Never
    mutates `state` itself -- correcting the record is `mark_merged_fn`'s
    job (the real CLI shells out to `loop_claim.py mark`, which re-verifies
    the SHA's ancestry before accepting it)."""
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
    return corrected


def _real_gh_query(branch: str, cwd: str) -> dict | None:
    try:
        proc = subprocess.run(
            ["gh", "pr", "view", branch, "--json", "state,mergeCommit"],
            cwd=cwd, capture_output=True, text=True, check=True,
        )
    except (subprocess.CalledProcessError, OSError):
        return None
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return None


def _real_mark_merged(unit_id: str, merged_sha: str, *, state_path: Path, project_root: str, shared_root: str) -> bool:
    result = subprocess.run([
        "uv", "run", str(Path(shared_root) / "scripts" / "lib" / "loop_claim.py"), "mark",
        "--state", str(state_path), "--unit", unit_id, "--status", "merged",
        "--force", "--confirm-no-task-running",
        "--campaign-worktree", project_root, "--merged-commit", merged_sha,
        "--reason", "held-merge reconciliation: GitHub reports this PR as merged although the unit was recorded held",
        "--operator", "campaign-mode:4-reconcile", "--reason-code", "held_merge_reconciled",
    ])
    return result.returncode == 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--shared-root", required=True)
    parser.add_argument("--deadline-seconds", type=float, default=DEFAULT_RECONCILE_SECONDS)
    parser.add_argument("--poll-interval-seconds", type=float, default=DEFAULT_POLL_INTERVAL_SECONDS)
    args = parser.parse_args(argv)

    state = json.loads(args.state.read_text(encoding="utf-8"))

    def mark_merged(unit_id: str, merged_sha: str) -> bool:
        return _real_mark_merged(unit_id, merged_sha, state_path=args.state,
                                  project_root=args.project_root, shared_root=args.shared_root)

    corrected = reconcile(
        state, project_root=args.project_root, gh_query_fn=_real_gh_query, mark_merged_fn=mark_merged,
        deadline_seconds=args.deadline_seconds, poll_interval_seconds=args.poll_interval_seconds,
    )
    for row in corrected:
        print(f"reconciled {row['id']} -> merged ({row['merged_sha']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
