#!/usr/bin/env python3
"""Per-unit campaign worktree checkout (campaign-dag-scheduler R2; wired into
the live wave-based campaign loop by R5a, "the flip").

This script's own job is narrow: compute the composite ``campaign-{slug}--{unit_id}
[-a{attempt}]`` worktree identity from validated inputs
(``lib.campaign_unit_worktree``, never a caller-trusted path string), fail
loudly on a total path length that would exceed Windows' ``MAX_PATH`` BEFORE
calling into ``setup_iterate_worktree.setup()`` (naming the campaign slug and
unit id, not an opaque mid-checkout git failure), then delegate to that
script's existing fresh-fetch / gitignore / cleanup behavior UNCHANGED via
its own ``slug`` parameter — this wrapper does not re-implement any of that.

Exit codes: mirrors ``setup_iterate_worktree.py`` (0 created/noop, 1 error,
2 collision, 3 fetch failed), plus two new ones specific to the per-unit
identity this wrapper adds on top:
- 4 — invalid ``--campaign-slug`` / ``--unit-id`` / ``--attempt`` (charset or
  shape reject — see ``lib.campaign_graph.id_charset_ok``)
- 5 — the resolved worktree path would exceed the Windows path-length bound

CLI:
    uv run shared/scripts/tools/setup_unit_worktree.py --project-root . \\
        --campaign-slug dag-scheduler --unit-id R2 --run-id iterate-... \\
        [--attempt 0] [--main main] [--session-id <id>] [--max-path 260]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

_SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from lib.campaign_unit_worktree import (  # noqa: E402
    WINDOWS_MAX_PATH,
    CampaignUnitWorktreeError,
    composite_worktree_name,
    path_length_error,
)
from lib.file_lock import LockTimeout  # noqa: E402
from lib.git_base import GitError, main_repo_root  # noqa: E402
from tools.setup_iterate_worktree import setup as setup_iterate_worktree  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Per-unit campaign worktree checkout.",
    )
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--campaign-slug", required=True,
                        help="Bare campaign slug, e.g. dag-scheduler (no campaign- prefix)")
    parser.add_argument("--unit-id", required=True, help="Sub-iterate id, e.g. R2")
    parser.add_argument("--attempt", type=int, default=0,
                        help="Retry attempt (R4); 0 = no -a{n} suffix")
    parser.add_argument("--max-path", type=int, default=WINDOWS_MAX_PATH,
                        help="Path-length bound override, for tests only "
                             "(default: the real Windows MAX_PATH)")
    parser.add_argument("--run-id", required=True,
                        help="Run id for the main-tree snapshot + run pointer")
    parser.add_argument("--main", default=None,
                        help="Default-branch override (else resolved from origin/HEAD)")
    parser.add_argument(
        "--session-id",
        default=os.environ.get("SHIPWRIGHT_SESSION_ID"),
        help="Session id for the run pointer (default: $SHIPWRIGHT_SESSION_ID)",
    )
    args = parser.parse_args(argv)

    project_root = Path(args.project_root).resolve()
    try:
        main_root = main_repo_root(project_root)
    except GitError as exc:
        payload = {"action": "error", "reason": "exception", "detail": str(exc)}
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 1

    try:
        slug = composite_worktree_name(args.campaign_slug, args.unit_id, attempt=args.attempt)
    except CampaignUnitWorktreeError as exc:
        payload = {"action": "error", "reason": "invalid_identity", "detail": str(exc)}
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 4

    length_error = path_length_error(main_root, args.campaign_slug, args.unit_id,
                                      attempt=args.attempt, max_path=args.max_path)
    if length_error:
        payload = {"action": "error", "reason": "path_too_long", "detail": length_error}
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 5

    try:
        exit_code, payload = setup_iterate_worktree(
            str(project_root), slug, args.run_id,
            main_override=args.main, session_id=args.session_id,
        )
    except (LockTimeout, GitError, OSError) as exc:
        exit_code, payload = 1, {
            "action": "error", "detail": str(exc),
            "reason": "triage_lock_timeout" if isinstance(exc, LockTimeout) else "exception",
        }

    print(json.dumps(payload, indent=2, ensure_ascii=False))
    if payload.get("detail"):
        print(f"setup_unit_worktree: {payload['detail']}", file=sys.stderr)
    for warning in payload.get("warnings", []):
        print(f"setup_unit_worktree: WARNING — {warning}", file=sys.stderr)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
