#!/usr/bin/env python3
"""Leak-guard for /shipwright-iterate worktree isolation (skill F0 + F11).

Fails closed when an iterate run is not properly isolated:

1. ``{project_root}`` does not resolve under ``<main_repo>/.worktrees/`` — the
   run is operating in the main tree or a stray worktree.
2. The main repo working tree carries uncommitted entries that were NOT
   present in the Step-1 snapshot — the run leaked changes into the main tree.

Attribution is snapshot-and-diff: ``setup_iterate_worktree.py`` records the
main tree's dirty paths at Step 1; this guard re-reads them and flags only
*new* paths, so pre-existing main-tree noise never blocks a run.

Exit codes:
- 0 — isolated (allowed to proceed)
- 1 — isolation violated (STOP)

CLI:
    uv run shared/scripts/checks/check_iterate_isolation.py \\
        --project-root . --run-id iterate-20260515-my-change [--stage f0|f11]
        [--json]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Wire up shared/scripts/lib.
_SHARED_LIB = Path(__file__).resolve().parents[1]
if str(_SHARED_LIB) not in sys.path:
    sys.path.insert(0, str(_SHARED_LIB))

from lib.worktree_isolation import (  # noqa: E402
    GitError,
    IsolationError,
    detect_leak,
    is_under_worktrees,
    is_worktree,
    main_repo_root,
)


def _decide(project_root: Path, run_id: str) -> tuple[int, dict]:
    """Return ``(exit_code, payload)`` for the isolation decision."""
    try:
        worktree = is_worktree(project_root)
    except GitError as exc:
        return 1, {
            "decision": "block",
            "reason": "not_a_git_repo",
            "detail": f"cannot resolve git context for {project_root}: {exc}",
        }

    main_root = main_repo_root(project_root)

    if not worktree or not is_under_worktrees(project_root, main_root):
        return 1, {
            "decision": "block",
            "reason": "not_under_worktrees",
            "detail": (
                f"{project_root} is not an iterate worktree under "
                f"{main_root}/.worktrees/ — every iterate run MUST execute in "
                "its own worktree. Re-run /shipwright-iterate so the "
                "Worktree Isolation step can create one."
            ),
        }

    try:
        clean, new_paths = detect_leak(main_root, run_id)
    except IsolationError as exc:
        return 1, {
            "decision": "block",
            "reason": "no_snapshot",
            "detail": str(exc),
        }

    if not clean:
        return 1, {
            "decision": "block",
            "reason": "main_tree_leak",
            "new_paths": new_paths,
            "detail": (
                f"{len(new_paths)} path(s) became dirty in the main repo "
                f"working tree ({main_root}) since this run started: "
                f"{', '.join(new_paths)}. An iterate run must never touch the "
                "main tree — investigate and revert before continuing."
            ),
        }

    return 0, {
        "decision": "allow",
        "reason": "isolated",
        "detail": (
            f"{project_root} is an isolated worktree; the main tree carries "
            "no run-attributable changes."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Leak-guard for /shipwright-iterate worktree isolation.",
    )
    parser.add_argument("--project-root", default=".")
    parser.add_argument(
        "--run-id",
        required=True,
        help="Run id — locates the Step-1 main-tree snapshot",
    )
    parser.add_argument(
        "--stage",
        default=None,
        choices=["f0", "f11"],
        help="Finalization stage invoking the guard (for messaging only)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit structured JSON to stdout (decision, reason, detail).",
    )
    args = parser.parse_args(argv)

    project_root = Path(args.project_root).resolve()
    exit_code, payload = _decide(project_root, args.run_id)
    if args.stage:
        payload["stage"] = args.stage

    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        verdict = "ALLOW" if exit_code == 0 else "BLOCK"
        stage = f" [{args.stage}]" if args.stage else ""
        print(f"check_iterate_isolation{stage}: {verdict} ({payload['reason']})")
        print(payload["detail"], file=sys.stderr)

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
