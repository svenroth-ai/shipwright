#!/usr/bin/env python3
"""Print session-role markers visible from `--project-root` as JSON.

Thin CLI wrapper around `shared/scripts/lib/session_role.detect_parallel_sessions`.
Replaces the inline `python -c` snippet in the iterate skill's B1c phase
(see SKILL.md) so adopted target projects can invoke it via the
`{shared_root}` placeholder convention used by every other shared script.

E spec MEDIUM-C1: extract inline snippets to keep B1c executable on
projects that don't carry `shared/scripts/lib/` at the literal path.

Usage:
    uv run "{shared_root}/scripts/tools/detect_parallel_sessions.py" \
        --project-root .
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Make `lib.session_role` importable when this script is invoked directly.
_SHARED_ROOT = Path(__file__).resolve().parent.parent
if str(_SHARED_ROOT) not in sys.path:
    sys.path.insert(0, str(_SHARED_ROOT))

from lib.session_role import detect_parallel_sessions  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--project-root",
        default=".",
        help="Project root or worktree path. The helper resolves the "
             "canonical main repo internally via `git rev-parse "
             "--git-common-dir`, so it is safe to invoke from a worktree.",
    )
    args = parser.parse_args(argv)
    found = detect_parallel_sessions(args.project_root)
    print(json.dumps(found, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
