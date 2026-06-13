#!/usr/bin/env python3
"""ensure_current — the F11 / campaign "refresh-if-behind" guard
(iterate-2026-06-12-automerge-serial-integrate — Auto-merge churn fix, Option A).

Bring an iterate branch current with ``origin/<default>`` THROUGH ``integrate_main``
(regenerating the derived snapshots) before its PR merges. GitHub's server-side
3-way auto-merge CANNOT run the regenerate-at-merge resolver, so a branch that
fell behind would merge stale (Group-E staleness) or stall DIRTY on the
regenerated-snapshot conflict. Caller:

  - F11 (every iterate, incl. campaign sub-iterates): refresh before arming
    ``gh pr merge --auto`` or handing the PR to the campaign orchestrator. The
    interleaved-serial campaign loop keeps ONE PR open at a time, so this is a
    clean no-op there — there is no separate end-stage drain.

A branch already current is a CLEAN no-op — ``integrate`` is never invoked
(nothing fetched-merged-committed) — so the common single-iterate auto-merge path
is unchanged. Thin wrapper over ``integrate_main.integrate`` (kept here, not in
integrate_main.py, so neither file crosses the 300-LOC bloat guideline).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent  # shared/scripts
sys.path.insert(0, str(_SCRIPTS_DIR))

from tools import integrate_main  # noqa: E402


def _behind_count(project_root: Path, ref: str) -> int | None:
    """Commits on ``ref`` not reachable from HEAD (``git rev-list --count HEAD..ref``).
    0 ⇒ HEAD is current/ahead; >0 ⇒ behind. None when the count can't be read."""
    proc = integrate_main._git(project_root, "rev-list", "--count", f"HEAD..{ref}", check=False)
    if proc.returncode != 0:
        return None
    try:
        return int(proc.stdout.strip())
    except ValueError:
        return None


def ensure_current(
    project_root: Path,
    run_id: str,
    *,
    merge_ref: str | None = None,
    default_branch: str | None = None,
    session_id: str | None = None,
    reason: str = "ensure-current pre-merge refresh",
    do_fetch: bool = True,
    regenerate: bool = True,
) -> dict:
    """Refresh-if-behind. Returns the JSON contract the F11 + campaign prose parse::

        {"status", "action": "already-current"|"integrated"|<failure-status>,
         "behind": int|None, "integrated": bool, "steps": [...]}

    ``integrated`` is True only when a commit was actually made, so the caller
    knows to re-push. ``action == already-current`` ⇒ the guard added nothing.
    """
    project_root = Path(project_root).resolve()
    steps: list[str] = []

    if do_fetch and os.environ.get("SHIPWRIGHT_ITERATE_NO_FETCH") != "1":
        fetched = integrate_main._git(project_root, "fetch", "origin", check=False)
        steps.append("fetched" if fetched.returncode == 0 else "fetch-failed")

    branch = default_branch or integrate_main._default_branch(project_root)
    ref = merge_ref or f"origin/{branch}"
    if integrate_main._git(
        project_root, "rev-parse", "--verify", "--quiet", ref, check=False
    ).returncode != 0:
        return {"status": "bad_ref", "ref": ref, "action": "bad_ref",
                "behind": None, "integrated": False, "steps": steps}

    behind = _behind_count(project_root, ref)
    if behind == 0:
        steps.append("already-current")
        return {"status": "ok", "action": "already-current", "behind": 0,
                "integrated": False, "steps": steps}

    # Behind (or count unreadable → integrate defensively; integrate() no-ops if it
    # turns out to be an ancestor). do_fetch=False: we already fetched above.
    head_before = integrate_main._git(project_root, "rev-parse", "HEAD", check=False).stdout.strip()
    result = integrate_main.integrate(
        project_root, run_id,
        merge_ref=ref, default_branch=branch, session_id=session_id,
        reason=reason, do_fetch=False, regenerate=regenerate,
    )
    head_after = integrate_main._git(project_root, "rev-parse", "HEAD", check=False).stdout.strip()
    # Did the branch actually move? Compare HEAD before/after rather than inferring
    # from integrate()'s internal step names — `integrated` is load-bearing (a
    # missed re-push would let auto-merge merge a STALE branch), so decouple it
    # from that step vocabulary so a future integrate() success path can't silently
    # flip it false while HEAD really advanced.
    made_commit = bool(head_before) and head_before != head_after
    if result.get("status") != "ok":
        action = result.get("status", "error")
    elif made_commit:
        action = "integrated"
    else:
        action = "already-current"  # race: count read >0 but ref was an ancestor by merge time

    merged = dict(result)
    merged["action"] = action
    merged["behind"] = behind
    merged["integrated"] = result.get("status") == "ok" and made_commit
    merged["steps"] = steps + result.get("steps", [])
    return merged


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Refresh an iterate branch with origin/<default> if behind, before it merges"
    )
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--merge-ref", default=None, help="override merge source (default origin/<default>)")
    parser.add_argument("--default-branch", default=None)
    parser.add_argument("--session-id", default=None)
    parser.add_argument("--reason", default="ensure-current pre-merge refresh")
    parser.add_argument("--no-fetch", action="store_true")
    parser.add_argument("--no-regenerate", action="store_true")
    args = parser.parse_args(argv)

    result = ensure_current(
        Path(args.project_root),
        args.run_id,
        merge_ref=args.merge_ref,
        default_branch=args.default_branch,
        session_id=args.session_id,
        reason=args.reason,
        do_fetch=not args.no_fetch,
        regenerate=not args.no_regenerate,
    )
    print(json.dumps(result, indent=2))
    # Reuse integrate_main's status→exit mapping so the two CLIs agree on codes
    # (ok→0, blocked→2, events/triage_invalid→4, bad_ref→5, merge_failed→6,
    # merge_commit_failed*→7, followup_commit_failed→8, else→3). already-current
    # carries status "ok" → 0, the guard's happy path.
    status = result.get("status")
    if status == "ok":
        return 0
    if status == "blocked":
        print(f"ABORT: non-churn conflicts — resolve by hand: {result.get('blocking')}", file=sys.stderr)
        return 2
    if status in ("events_invalid", "triage_invalid"):
        return 4
    if status == "bad_ref":
        print(f"ABORT: merge ref does not resolve: {result.get('ref')}", file=sys.stderr)
        return 5
    if status == "merge_failed":
        return 6
    if status in ("merge_commit_failed", "merge_commit_failed_abort_incomplete"):
        return 7
    if status == "followup_commit_failed":
        return 8
    return 3


if __name__ == "__main__":
    raise SystemExit(main())
