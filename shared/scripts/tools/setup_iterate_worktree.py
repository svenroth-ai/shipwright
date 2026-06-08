#!/usr/bin/env python3
"""Unconditional worktree setup for /shipwright-iterate (skill Step "Worktree
Isolation").

Every iterate run executes in its own git worktree + branch — structurally, not
by opt-in detection. This script is the mechanism:

- Invoked from the MAIN repo  → ``git fetch origin`` → create
  ``.worktrees/<slug>`` on a new ``iterate/<slug>`` branch cut from freshly
  fetched ``origin/<default>`` → snapshot the main tree → write the run
  pointer → print the worktree path as the skill's new ``{project_root}``.
- Invoked from inside a worktree → no-op; ``{project_root}`` is the cwd.

Output: a single JSON object on stdout (the machine contract — the skill reads
``.project_root`` from it). Human-readable notes go to stderr.

Exit codes:
- 0 — worktree created, or no-op (already inside a worktree)
- 1 — unexpected error (bad args, git failure)
- 2 — slug collision (worktree dir or ``iterate/<slug>`` branch already exists)
- 3 — ``git fetch origin`` failed and ``SHIPWRIGHT_ITERATE_NO_FETCH`` is not set

Offline override: set ``SHIPWRIGHT_ITERATE_NO_FETCH=1`` to skip the fetch and
branch from the local ``origin/<default>`` ref (the run may then start from a
stale base — that is the deliberate trade-off the operator accepts).

CLI:
    uv run shared/scripts/tools/setup_iterate_worktree.py \\
        --project-root . \\
        --slug my-change \\
        --run-id iterate-20260515-my-change \\
        [--main main] [--session-id <id>]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# Wire up shared/scripts/lib.
_SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from lib.gitattributes_union import self_heal_gitattributes  # noqa: E402
from lib.gitignore_selfheal import self_heal_gitignore  # noqa: E402
from lib.sweep_outbox import sweep_outbox_to_branch  # noqa: E402
from lib.worktree_isolation import (  # noqa: E402
    GitError,
    WORKTREES_DIRNAME,
    branch_exists,
    current_branch,
    default_branch,
    is_worktree,
    main_repo_root,
    prune_stale_run_pointers,
    run_git,
    snapshot_path,
    write_run_pointer,
    write_snapshot,
)

_NO_FETCH_ENV = "SHIPWRIGHT_ITERATE_NO_FETCH"


def _do_fetch(main_root: Path) -> tuple[bool, str]:
    """Fetch origin. Returns ``(ok_to_continue, detail)``.

    ``ok_to_continue`` is False only when the fetch failed AND the offline
    override is not set — that is the hard-fail path (exit 3).
    """
    if os.environ.get(_NO_FETCH_ENV) == "1":
        return True, f"fetch skipped ({_NO_FETCH_ENV}=1) — branching from local refs"
    try:
        run_git(["fetch", "origin"], cwd=main_root, timeout=120.0)
        return True, "fetched origin"
    except GitError as exc:
        return False, f"git fetch origin failed: {exc}"


def _resolve_base_ref(main_root: Path, branch: str) -> tuple[str, str | None]:
    """Prefer ``origin/<branch>``; fall back to the local branch with a warning."""
    remote_ref = f"origin/{branch}"
    probe = run_git(
        ["rev-parse", "--verify", "--quiet", remote_ref],
        cwd=main_root,
        check=False,
    )
    if probe.returncode == 0:
        return remote_ref, None
    return branch, (
        f"{remote_ref} not found — branching from local {branch!r}; "
        "the base may be stale"
    )


def setup(
    project_root: str,
    slug: str,
    run_id: str,
    *,
    main_override: str | None = None,
    session_id: str | None = None,
) -> tuple[int, dict]:
    """Perform unconditional worktree setup. Returns ``(exit_code, payload)``."""
    root = Path(project_root).resolve()

    # 1. Already inside a worktree → no new worktree, but still ensure the
    #    per-session run pointer + the main-tree snapshot exist so the F0/F11
    #    leak-guard has a baseline to diff against (otherwise it fail-closes
    #    with reason=no_snapshot). The snapshot is written only if missing —
    #    a re-invocation must never clobber the original Step-1 baseline.
    if is_worktree(root):
        main_root = main_repo_root(root)
        pointer_path = write_run_pointer(
            main_root,
            run_id=run_id,
            slug=slug,
            branch=current_branch(root),
            worktree_path=root,
            session_id=session_id,
        )
        snap = snapshot_path(main_root, run_id)
        snapshot_written = False
        if not snap.exists():
            write_snapshot(main_root, run_id)
            snapshot_written = True
        prune_stale_run_pointers(main_root)
        return 0, {
            "action": "noop",
            "in_worktree": True,
            "project_root": str(root),
            "branch": current_branch(root),
            "main_root": str(main_root),
            "snapshot_path": str(snap),
            "pointer_path": str(pointer_path),
            "snapshot_written": snapshot_written,
            "detail": "already inside a linked worktree; ensured run pointer + snapshot",
        }

    main_root = main_repo_root(root)
    branch = f"iterate/{slug}"
    worktree_path = main_root / WORKTREES_DIRNAME / slug

    # 2. Slug collision — refuse cleanly, leave no partial state.
    if worktree_path.exists():
        return 2, {
            "action": "collision",
            "reason": "worktree_exists",
            "project_root": str(main_root),
            "detail": (
                f"{worktree_path} already exists — pick a different slug or "
                f"run: git worktree remove {worktree_path}"
            ),
        }
    if branch_exists(main_root, branch):
        return 2, {
            "action": "collision",
            "reason": "branch_exists",
            "project_root": str(main_root),
            "detail": (
                f"branch {branch!r} already exists — pick a different slug or "
                f"run: git branch -D {branch}"
            ),
        }

    # 3. Fresh fetch so the branch base is never stale.
    fetched, fetch_detail = _do_fetch(main_root)
    if not fetched:
        return 3, {
            "action": "fetch_failed",
            "reason": "fetch_failed",
            "project_root": str(main_root),
            "detail": (
                f"{fetch_detail}. Set {_NO_FETCH_ENV}=1 to branch from local "
                "refs anyway (deliberate offline use)."
            ),
        }

    # 4. Resolve base ref + create the worktree.
    db = default_branch(main_root, main_override)
    base_ref, base_warning = _resolve_base_ref(main_root, db)
    try:
        run_git(
            ["worktree", "add", str(worktree_path), "-b", branch, base_ref],
            cwd=main_root,
        )
        base_commit = run_git(
            ["rev-parse", base_ref], cwd=main_root
        ).stdout.strip()
    except GitError as exc:
        return 1, {
            "action": "error",
            "reason": "worktree_add_failed",
            "project_root": str(main_root),
            "detail": str(exc),
        }

    # 4.5/4.6. Self-heal the canon scaffolds into the new worktree as chore commits
    #      (→ ship in PR; guarded fail-soft no-op in the monorepo): the append-log
    #      union .gitattributes AND the canonical .shipwright/ .gitignore block
    #      (D3 — keeps the triage.outbox.jsonl buffer ignored in stale-cache repos).
    for _label, _heal in (("gitattributes", self_heal_gitattributes(worktree_path)),
                          ("gitignore", self_heal_gitignore(worktree_path))):
        if _heal.status == "error":
            print(f"setup_iterate_worktree: {_label} self-heal {_heal.reason}",
                  file=sys.stderr)

    # 5. SWEEP the gitignored main-tree triage outbox into THIS worktree's tracked
    #    triage.jsonl + commit on iterate/<slug> BEFORE snapshotting (campaign
    #    2026-06-08 / D2): appends ride the PR to origin, not local main. Step-3
    #    refreshed origin/<default> for the GC. Surface any non-clean sweep so a
    #    caller never assumes delivery (skip recoverable next setup). lib/sweep_outbox.
    sweep = sweep_outbox_to_branch(main_root, worktree_path, default_branch=db)
    sweep_warning = (f"sweep-outbox {sweep.status}: {sweep.errors or sweep.reason}"
                     if sweep.status in ("invalid", "error", "skipped") else None)
    if sweep.status in ("invalid", "error"):
        print(f"setup_iterate_worktree: {sweep_warning}", file=sys.stderr)

    # 6. Snapshot the main tree + write the per-session run pointer.
    snap_path = write_snapshot(main_root, run_id)
    pointer_path = write_run_pointer(
        main_root,
        run_id=run_id,
        slug=slug,
        branch=branch,
        worktree_path=worktree_path,
        session_id=session_id,
    )
    prune_stale_run_pointers(main_root)

    warnings = [w for w in (fetch_detail, base_warning, sweep_warning) if w]
    return 0, {
        "action": "created",
        "in_worktree": False,
        "project_root": str(worktree_path),
        "branch": branch,
        "base_ref": base_ref,
        "base_commit": base_commit,
        "default_branch": db,
        "main_root": str(main_root),
        "snapshot_path": str(snap_path),
        "pointer_path": str(pointer_path),
        "run_id": run_id,
        "warnings": warnings,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Unconditional worktree setup for /shipwright-iterate.",
    )
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--slug", required=True,
                        help="Iterate slug — branch iterate/<slug>, worktree .worktrees/<slug>")
    parser.add_argument("--run-id", required=True,
                        help="Run id — identifies the main-tree snapshot + run pointer")
    parser.add_argument("--main", default=None,
                        help="Default-branch override (else resolved from origin/HEAD)")
    parser.add_argument(
        "--session-id",
        default=os.environ.get("SHIPWRIGHT_SESSION_ID"),
        help="Session id for the run pointer (default: $SHIPWRIGHT_SESSION_ID)",
    )
    args = parser.parse_args(argv)

    try:
        exit_code, payload = setup(
            args.project_root,
            args.slug,
            args.run_id,
            main_override=args.main,
            session_id=args.session_id,
        )
    except (GitError, OSError) as exc:
        exit_code, payload = 1, {
            "action": "error",
            "reason": "exception",
            "detail": str(exc),
        }

    print(json.dumps(payload, indent=2, ensure_ascii=False))
    if payload.get("detail"):
        print(f"setup_iterate_worktree: {payload['detail']}", file=sys.stderr)
    for warning in payload.get("warnings", []):
        print(f"setup_iterate_worktree: WARNING — {warning}", file=sys.stderr)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
