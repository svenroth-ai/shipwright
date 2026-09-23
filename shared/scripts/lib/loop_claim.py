"""Ready-set computation + atomic claim/release for ``kind == "sub_iterate"``
campaigns — the "claim" half of R4's claim mechanics (identity-checked
mutation lives in the sibling ``lib.loop_mark``; see that module's docstring
for why the split). Campaign ``campaign-dag-scheduler`` R4. Batch-parallel
sibling of ``autonomous_loop.py``'s single-unit ``cmd_next``/``cmd_record``;
NEVER touches `kind == "section"` state.

Single CLI entry point for all five R4 commands (``next-batch``, ``release``,
``mark``, ``mark-running``, ``mark-merged``) — ``main()`` dispatches the last
three into ``lib.loop_mark``, so a caller never needs to know about the
internal module split.

- ``next-batch`` — computes the bounded ready set (reusing
  ``lib.loop_state.is_unit_ready``/``describe_blocker``) and claims
  ``min(--max-parallel, |ready_set|)`` atomically under ``loop.lock``.
- ``release`` — launch-failure path: a unit still ``claimed`` at wave-return
  goes back to ``pending`` (or ``failed`` once ``--max-attempts`` exhausted).

Import convention: ``lib.``-qualified for ``loop_state``; ``branch_base``/
``file_lock`` stay bare-sibling-imported (one module identity, never two).

Exit codes: 0 success · 1 invalid args/structural failure · 2 ``next-batch``
done (all `TERMINAL`) · 4 ``next-batch`` stalled (not done, nothing ready)
· 5 fencing-token mismatch (mirrors ``cmd_record``'s own) · 6 ``LockTimeout``.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:  # bare-sibling — see module docstring's import-convention note
    from branch_base import fresh_remote_default_ref
except ImportError:  # pragma: no cover
    fresh_remote_default_ref = None  # type: ignore[assignment]
from file_lock import LockTimeout, file_lock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lib.campaign_session_lock import DEFAULT_STALE_AFTER_SECONDS  # noqa: E402
from lib.campaign_unit_worktree import (  # noqa: E402
    CampaignUnitWorktreeError,
    resolved_worktree_path,
)
from lib.git_base import GitError, main_repo_root  # noqa: E402
from lib.loop_mark import cmd_mark, cmd_mark_merged, cmd_mark_running  # noqa: E402
from lib.loop_state import (  # noqa: E402
    TERMINAL,
    describe_blocker,
    find_unit_row,
    is_unit_ready,
    is_valid_sha,
    now_iso,
    validate_attempt_token,
)

#: Framework hard cap — not configurable higher (bounds concurrent Task calls).
MAX_PARALLEL_HARD_CAP = 8


def _load_state(state_path: Path) -> dict:
    return json.loads(state_path.read_text(encoding="utf-8"))


def _save_state(state_path: Path, state: dict) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = state_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(state_path)


def _is_ancestor(commit: str, base: str, *, cwd: str | None = None) -> bool:
    try:
        r = subprocess.run(["git", "merge-base", "--is-ancestor", commit, base],
                            capture_output=True, text=True, timeout=15, cwd=cwd)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False
    return r.returncode == 0


def _ancestry_ok(unit: dict, all_units: list[dict], base_branch: str | None, *, cwd: str | None = None) -> bool:
    """Try once without fetching; on failure, fetch origin once and retry;
    still absent -> leave ``pending`` for the next call. `base_branch=None`
    fails closed for a unit with real dependencies."""
    deps = unit.get("depends_on") or []
    if not deps:
        return True
    if not base_branch:
        return False
    by_id = {str(u.get("id")).lower(): u for u in all_units}
    for dep_id in deps:
        dep = by_id.get(str(dep_id).lower())
        commit = dep.get("merged_commit") if dep else None
        if not commit or not is_valid_sha(commit):
            return False
        if _is_ancestor(commit, base_branch, cwd=cwd):
            continue
        try:
            subprocess.run(["git", "fetch", "origin"], capture_output=True, text=True, timeout=60, cwd=cwd)
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False
        if not _is_ancestor(commit, base_branch, cwd=cwd):
            return False
    return True


def _resolve_batch_base(strategy: str, *, cwd: str | None) -> str | None:
    """`serial`/`independent` only — `stacked` has no single base for a
    parallel ready set (out of scope) and resolves to ``None``."""
    if strategy == "serial":
        return fresh_remote_default_ref(cwd=cwd) if fresh_remote_default_ref else None
    if strategy == "independent":
        return "main"
    return None


def _claim_unit(unit: dict, loop_id: str) -> tuple[int, str]:
    """First-ever claim: no bump. A unit already carrying an `attempt_id`
    (reclaimed to `pending` before) increments — a reclaim never bumps
    `attempt`; only the unit's next claim does."""
    if unit.get("attempt_id") is None:
        attempt = unit.get("attempt", 0)
    else:
        attempt = unit.get("attempt", 0) + 1
    attempt_id = f"{loop_id}-{unit['id']}-a{attempt}"
    unit["attempt"] = attempt
    unit["attempt_id"] = attempt_id
    unit["status"] = "claimed"
    unit["claimed_at"] = now_iso()
    # Claim-time lease start — else the unit reads "never leased" and gets
    # reclaimed (burning an attempt) before its runner's first heartbeat.
    unit["lease_expires_at"] = time.time() + DEFAULT_STALE_AFTER_SECONDS
    return attempt, attempt_id


def _snapshot_merged_commits(units: list[dict]) -> dict[str, str]:
    """``{case-folded unit_id: merged_commit}`` for every `merged` unit —
    detects, without I/O, whether a dependency changed between the
    outside-lock ancestry pass and the in-lock claim. Keyed case-folded,
    matching every other dependency lookup in this module
    (`_ancestry_ok`'s `by_id`) — `campaign_graph.validate_dependency_graph`
    accepts a case-mismatched `depends_on` edge at write time, so a bare
    exact-case key would return `None` for both snapshots on such an edge
    and let the staleness comparison pass vacuously."""
    return {str(u["id"]).lower(): u.get("merged_commit") for u in units if u.get("status") == "merged"}


def cmd_next_batch(args: argparse.Namespace) -> int:
    state_path = Path(args.state)
    max_parallel = args.max_parallel
    if isinstance(max_parallel, bool) or not isinstance(max_parallel, int) \
            or max_parallel <= 0 or max_parallel > MAX_PARALLEL_HARD_CAP:
        print(f"ERROR: --max-parallel must be a positive integer <= {MAX_PARALLEL_HARD_CAP}, "
              f"got {max_parallel!r}", file=sys.stderr)
        return 1

    # Read-only peek — atomic tmp+replace means no lock is needed just to read.
    state_peek = _load_state(state_path)
    if state_peek.get("kind") != "sub_iterate":
        print("ERROR: next-batch is only valid for kind == 'sub_iterate'", file=sys.stderr)
        return 1

    # Base ref + ancestry pre-check both run OUTSIDE loop.lock — each can
    # fetch (60s timeout), a starvation hazard inside a 30s-timeout lock.
    strategy = state_peek.get("branch_strategy", "single-branch")
    base_branch = _resolve_batch_base(strategy, cwd=args.campaign_worktree)
    if base_branch is None:
        # External Tier-3 PR review (GPT, round 6): a `None` base must never
        # reach the ready-set computation below — `_ancestry_ok` returns True
        # unconditionally for a dependency-free unit regardless of
        # `base_branch`, so this would silently claim those units with
        # `"base_branch": null` while dependency-bearing units stall forever
        # with no error at all (`_ancestry_ok` fails closed for THEM, but
        # nothing ever reports why). `next-batch` only supports the
        # strategies that resolve a real base ('serial'/'independent');
        # reject everything else — including 'stacked' (deprecated at
        # write time, campaign_init.py) and any unrecognized value — up
        # front, before any ancestry/claim processing.
        print(f"ERROR: branch_strategy {strategy!r} has no batch base for next-batch "
              "(only 'serial'/'independent' are supported)", file=sys.stderr)
        return 1

    pre_units = state_peek["units"]
    pre_snapshot = _snapshot_merged_commits(pre_units)
    # External Tier-3 PR review (GPT, round 11): `ancestry_confirmed` proves a
    # unit's dependency SHAs (as of the peek) actually verify as ancestors —
    # but that proof is only as good as the `depends_on` edge set it was
    # computed against. A concurrent writer that ADDS a new edge to an
    # already-`pending` unit between the peek and the lock is invisible to
    # the SHA-staleness check below whenever the new dependency's own
    # `merged_commit` happens not to change in that same window (it was
    # already merged before the peek and stays that way) — the snapshot
    # comparison passes vacuously for an edge it never even looked at, so a
    # unit could be claimed with a brand-new dependency whose ancestry
    # `_ancestry_ok` never actually checked. Snapshotting the exact edge SET
    # each pending unit carried at peek time, and requiring the locked
    # reload's set to match exactly, closes that gap the same way the SHA
    # snapshot closes the "did an already-known dependency's commit move"
    # case.
    pre_depends_on = {
        u["id"]: frozenset(str(d).lower() for d in (u.get("depends_on") or []))
        for u in pre_units
    }
    ancestry_confirmed = {
        u["id"] for u in pre_units
        if u["status"] == "pending" and is_unit_ready(u, pre_units)
        and _ancestry_ok(u, pre_units, base_branch, cwd=args.campaign_worktree)
    }

    try:
        with file_lock(state_path.parent / "loop.lock", timeout_seconds=30):
            state = _load_state(state_path)
            # External Tier-3 PR review (GPT, round 10): the unlocked peek
            # above checked `kind` before this lock was acquired — a
            # concurrent `cmd_init` can replace the state file with a
            # `kind == "section"` one in that window. Re-check on the
            # locked reload, before any unit is inspected or mutated, so
            # this command's documented guarantee (module docstring: NEVER
            # touches `kind == "section"` state) holds under the race too,
            # not just on the initial read.
            if state.get("kind") != "sub_iterate":
                print("ERROR: next-batch is only valid for kind == 'sub_iterate' "
                      "(state changed kind while lock was being acquired)", file=sys.stderr)
                return 1
            units = state["units"]
            loop_id = state["loop_id"]
            fresh_snapshot = _snapshot_merged_commits(units)

            ready = [
                u for u in units
                if u["status"] == "pending"
                and is_unit_ready(u, units)
                and u["id"] in ancestry_confirmed
                # The dependency EDGE SET itself is unchanged since the
                # outside-lock ancestry pass ran against it (round 11) —
                # a unit whose `depends_on` gained or lost an edge in that
                # window is excluded this round rather than trusted on a
                # verification that covered a different edge set; it is
                # reconsidered on the next `next-batch` call, whose own
                # outside-lock pass will check its current edges for real.
                and frozenset(str(d).lower() for d in (u.get("depends_on") or [])) == pre_depends_on.get(u["id"])
                # Deps' SHAs unchanged since the outside-lock pass verified
                # them — case-folded lookup, see `_snapshot_merged_commits`.
                and all(fresh_snapshot.get(str(dep_id).lower()) == pre_snapshot.get(str(dep_id).lower())
                        for dep_id in (u.get("depends_on") or []))
            ]
            claim_n = min(max_parallel, len(ready))
            claimed = []
            for unit in ready[:claim_n]:
                attempt, attempt_id = _claim_unit(unit, loop_id)
                claimed.append({
                    "id": unit["id"], "spec_path": unit.get("spec_path", ""),
                    "attempt": attempt, "attempt_id": attempt_id,
                    "base_branch": base_branch, "depends_on": unit.get("depends_on", []),
                })

            if claimed:
                _save_state(state_path, state)
                print(json.dumps({"claimed": claimed, "ready_count": len(ready), "loop_id": loop_id}))
                return 0

            if all(u["status"] in TERMINAL for u in units):
                print(json.dumps({"claimed": [], "done": True, "reason": "All units processed"}))
                return 2

            pending = [u for u in units if u["status"] == "pending"]
            print(json.dumps({
                "claimed": [], "done": False,
                "reason": "Batch stalled: no ready units this round",
                "blocked_pending_ids": [u["id"] for u in pending],
                "blockers": [describe_blocker(u, units) for u in pending],
            }))
            return 4
    except LockTimeout as exc:
        print(json.dumps({"error": "lock_timeout", "detail": str(exc)}), file=sys.stderr)
        return 6


def _cleanup_unit_worktree(campaign_worktree: str, campaign_slug: str, unit_id: str, attempt: int) -> None:
    """Best-effort ``git worktree remove`` + ``git branch -D`` (never blocks
    the logical release — swallow every failure, e.g. a Windows file-lock;
    the spec names ``git worktree prune`` at the next claim as the intended
    fallback for that case, but no such call exists in this codebase yet —
    see the review-findings ADR's finding #5 correction). Path always
    RECOMPUTED from validated ``(slug, unit_id, attempt)`` via
    ``lib.campaign_unit_worktree`` — never a stored path. Branch name is not
    owned here (its ``{desc}`` suffix is R5a's job); read back from git's
    own checked-out ref instead — authoritative, not trusted metadata.

    Stage-3 doubt review (HIGH #4): ``resolved_worktree_path``'s first
    parameter is ``main_root`` — the repo root ABOVE ``.worktrees/`` — but
    ``campaign_worktree`` (this function's own parameter) is ALREADY
    ``<main_root>/.worktrees/campaign-{slug}`` (``campaign_unit_worktree.py``'s
    own docs; ``setup_unit_worktree.py``'s correct usage). Passing
    ``campaign_worktree`` straight through computed a doubled, nonexistent
    path, hit the ``wt_path.exists()`` guard below, and silently no-op'd this
    entire cleanup on every call. Resolve the real ``main_root`` first, the
    same way ``setup_unit_worktree.py`` does."""
    try:
        main_root = main_repo_root(Path(campaign_worktree))
    except (GitError, OSError, subprocess.TimeoutExpired):
        return  # best-effort — never blocks the logical release above
    try:
        wt_path = resolved_worktree_path(main_root, campaign_slug, unit_id, attempt=attempt)
    except CampaignUnitWorktreeError:
        return
    if not wt_path.exists():
        return
    try:
        branch = subprocess.run(["git", "-C", str(wt_path), "rev-parse", "--abbrev-ref", "HEAD"],
                                 capture_output=True, text=True, timeout=15).stdout.strip()
        subprocess.run(["git", "-C", campaign_worktree, "worktree", "remove", "--force", str(wt_path)],
                        capture_output=True, text=True, timeout=30)
        if branch and branch != "HEAD":
            subprocess.run(["git", "-C", campaign_worktree, "branch", "-D", branch],
                            capture_output=True, text=True, timeout=15)
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass  # best-effort — never blocks the logical release above


def cmd_release(args: argparse.Namespace) -> int:
    """`claimed -> pending` (no attempt re-bump), or `-> failed` once
    `--max-attempts` (default 3) is exhausted. `attempt` is 0-indexed, so
    `--max-attempts K` permits exactly `K` total claims. Physical worktree/
    branch cleanup (best-effort, never blocking) runs AFTER the logical
    release is durably saved — see `_cleanup_unit_worktree`."""
    state_path = Path(args.state)
    # External Tier-3 PR review (GPT, round 12): argparse's `type=int` alone
    # accepts zero and negative values, and `unit.get("attempt", 0) + 1 >=
    # args.max_attempts` is then trivially true for any such value (attempt
    # is always >= 0) — every release would silently mark the unit `failed`
    # on its very first retry, with no valid attempt budget ever having
    # existed. Mirrors `cmd_next_batch`'s own `--max-parallel` validation.
    if isinstance(args.max_attempts, bool) or not isinstance(args.max_attempts, int) \
            or args.max_attempts <= 0:
        print(f"ERROR: --max-attempts must be a positive integer, got {args.max_attempts!r}",
              file=sys.stderr)
        return 1
    try:
        with file_lock(state_path.parent / "loop.lock", timeout_seconds=30):
            state = _load_state(state_path)
            # External review (GPT, high): this module's own docstring
            # promises it NEVER touches `kind == "section"` state — `cmd_
            # next_batch` already enforces that, but `cmd_release` had no
            # equivalent gate, letting a wrong `--state` path (or a caller
            # unaware of the new CLI) write the 9-state vocabulary into a
            # legacy section row's `status` field.
            if state.get("kind") != "sub_iterate":
                print("ERROR: release is only valid for kind == 'sub_iterate'", file=sys.stderr)
                return 1
            unit = find_unit_row(state, args.unit)
            if unit is None:
                print(f"ERROR: unit {args.unit!r} not found", file=sys.stderr)
                return 1
            if not validate_attempt_token(unit, args.attempt_id):
                print(json.dumps({"released": False, "status": "stale_attempt", "unit": args.unit}))
                return 5
            if unit["status"] != "claimed":
                print(f"ERROR: cannot release unit {args.unit!r} from status {unit['status']!r} "
                      "(only 'claimed' is releasable)", file=sys.stderr)
                return 1

            exhausted = unit.get("attempt", 0) + 1 >= args.max_attempts
            unit["status"] = "failed" if exhausted else "pending"
            unit["released_at"] = now_iso()
            attempt = unit.get("attempt", 0)
            _save_state(state_path, state)
            print(json.dumps({"released": True, "unit": args.unit, "status": unit["status"]}))
    except LockTimeout as exc:
        print(json.dumps({"error": "lock_timeout", "detail": str(exc)}), file=sys.stderr)
        return 6

    campaign_slug = getattr(args, "campaign_slug", None)
    campaign_worktree = getattr(args, "campaign_worktree", None)
    if campaign_slug and campaign_worktree:
        try:  # belt-and-suspenders — the release above already landed.
            _cleanup_unit_worktree(campaign_worktree, campaign_slug, args.unit, attempt)
        except Exception:
            pass
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Atomic claim + fencing mutators for campaign sub-iterates")
    sub = parser.add_subparsers(dest="command", required=True)

    p_batch = sub.add_parser("next-batch", help="Compute + claim the bounded ready set")
    p_batch.add_argument("--state", required=True)
    p_batch.add_argument("--campaign-worktree", required=True,
                          help="cwd for every git call this command makes (base-ref resolution, ancestry asserts)")
    p_batch.add_argument("--max-parallel", type=int, required=True)

    p_release = sub.add_parser("release", help="claimed -> pending|failed (launch failure)")
    p_release.add_argument("--state", required=True)
    p_release.add_argument("--unit", required=True)
    p_release.add_argument("--attempt-id", required=True)
    p_release.add_argument("--max-attempts", type=int, default=3)
    p_release.add_argument("--campaign-slug", required=True,
                            help="recomputes the released unit's worktree path for best-effort cleanup")
    p_release.add_argument("--campaign-worktree", required=True,
                            help="cwd for the cleanup's git calls (worktree remove / branch -D)")

    p_running = sub.add_parser("mark-running", help="claimed -> running")
    p_running.add_argument("--state", required=True)
    p_running.add_argument("--unit", required=True)
    p_running.add_argument("--attempt-id", required=True)

    p_merged = sub.add_parser("mark-merged", help="merging -> merged")
    p_merged.add_argument("--state", required=True)
    p_merged.add_argument("--unit", required=True)
    p_merged.add_argument("--attempt-id", required=True)
    p_merged.add_argument("--merged-commit", required=True)

    p_mark = sub.add_parser("mark", help="Audited operator override — may cross any edge")
    p_mark.add_argument("--state", required=True)
    p_mark.add_argument("--unit", required=True)
    p_mark.add_argument("--status", required=True)
    p_mark.add_argument("--reason", required=True)
    p_mark.add_argument("--operator", required=True)
    p_mark.add_argument("--reason-code", default=None)
    p_mark.add_argument("--merged-commit", default=None)
    p_mark.add_argument("--force", action="store_true")
    p_mark.add_argument("--confirm-no-task-running", action="store_true")
    p_mark.add_argument("--campaign-worktree", default=None, help="required for --status merged")

    args = parser.parse_args()
    cmd_map = {
        "next-batch": cmd_next_batch,
        "release": cmd_release,
        "mark-running": cmd_mark_running,
        "mark-merged": cmd_mark_merged,
        "mark": cmd_mark,
    }
    return cmd_map[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
