#!/usr/bin/env python3
"""Persist a session role marker via session_role.write_role().

Thin CLI wrapper around `shared/scripts/lib/session_role.write_role`.
Replaces the inline `python -c` snippet in the iterate skill's B1c step 5
so adopted target projects can invoke it via the `{shared_root}`
placeholder convention used by every other shared script.

E spec MEDIUM-C1: extract inline snippets to keep B1c executable on
projects that don't carry `shared/scripts/lib/` at the literal path.

Usage:
    uv run "{shared_root}/scripts/tools/write_session_role.py" \
        --project-root . \
        --role canonical \
        --session-id "$SHIPWRIGHT_SESSION_ID" \
        --worktree-path "$(pwd)" \
        --notes "primary repo"
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# Make `lib.session_role` importable when this script is invoked directly.
_SHARED_ROOT = Path(__file__).resolve().parent.parent
if str(_SHARED_ROOT) not in sys.path:
    sys.path.insert(0, str(_SHARED_ROOT))

from lib.session_role import VALID_ROLES, write_role  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", default=".")
    parser.add_argument(
        "--role",
        required=True,
        choices=VALID_ROLES,
        help="Session role: canonical (pushes for the repo) or "
             "secondary (does not push without explicit auth).",
    )
    parser.add_argument(
        "--session-id",
        default=os.environ.get("SHIPWRIGHT_SESSION_ID", ""),
        help="Defaults to SHIPWRIGHT_SESSION_ID env var.",
    )
    parser.add_argument(
        "--worktree-path",
        default=str(Path.cwd().resolve()),
        help="Defaults to the current working directory.",
    )
    parser.add_argument("--notes", default="")
    args = parser.parse_args(argv)

    payload = write_role(
        project_root=args.project_root,
        role=args.role,
        session_id=args.session_id,
        worktree_path=args.worktree_path,
        notes=args.notes,
    )
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
