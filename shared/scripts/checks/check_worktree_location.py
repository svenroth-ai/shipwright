#!/usr/bin/env python3
"""Location-only isolation guard: is ``{project_root}`` an iterate worktree?

Used by the campaign orchestrator immediately before it spawns a
``sub-iterate-runner`` subagent, and by the runner itself at Step 1.0, before
either touches git. Two production campaigns had a runner mutate branches
directly in the main repository checkout, because a freshly spawned
subagent's shell does not inherit the orchestrator's own ``cd`` into the
campaign worktree.

Distinct from ``check_iterate_isolation.py`` (the F0/F11 leak-guard): that
script ALSO diffs the main tree against a Step-1 snapshot keyed by
``run_id``. That diff is wrong for a campaign sub-iterate — it never calls
``setup_iterate_worktree.py`` for its own ``run_id`` (no snapshot exists),
and ``campaign-mode.md`` step 3h deliberately writes the live board's
``status.json`` into the MAIN tree between sub-iterate builds, which a
snapshot diff would misreport as a leak. This check answers only the
location question, with no snapshot and no ``run_id``.

Exit codes:
- 0 — {project_root} is a worktree under <main_repo>/.worktrees/
- 1 — it is not (main repo checkout, stray directory, or not a git repo)

CLI:
    uv run shared/scripts/checks/check_worktree_location.py \\
        --project-root . [--json]
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

from lib.worktree_location import worktree_location_error  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Location-only worktree-isolation guard (campaign spawn gate).",
    )
    parser.add_argument("--project-root", default=".")
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit structured JSON to stdout (decision, detail).",
    )
    args = parser.parse_args(argv)

    project_root = Path(args.project_root).resolve()
    detail = worktree_location_error(project_root)
    exit_code = 1 if detail else 0
    payload = {
        "decision": "block" if detail else "allow",
        "project_root": str(project_root),
        "detail": detail or f"{project_root} is an isolated worktree.",
    }

    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        verdict = "BLOCK" if exit_code else "ALLOW"
        print(f"check_worktree_location: {verdict}")
        print(payload["detail"], file=sys.stderr if exit_code else sys.stdout)

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
