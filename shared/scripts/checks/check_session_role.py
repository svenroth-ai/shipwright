#!/usr/bin/env python3
"""Push guardrail for parallel-iterate sessions.

Consulted by F11 (Push) and the runner Step 5 push. Blocks `git push`
from a `secondary` role unless `SHIPWRIGHT_SECONDARY_PUSH_AUTH=1` is
set.

Exit codes:
- 0 — push allowed (canonical role, missing marker, or env override)
- 1 — push blocked (secondary role + no env override)

The default-permissive on missing marker is intentional: most
projects run single-session and shouldn't be gated.

Usage:
    uv run shared/scripts/checks/check_session_role.py
    uv run shared/scripts/checks/check_session_role.py --project-root /path/to/repo

Returns rationale on stderr; pre-push hooks can grep stdout for
JSON if a structured signal is needed (`--json` flag).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# Wire up shared/scripts/lib so we can import session_role.
# parents[0]=checks, [1]=scripts, [2]=shared.
_SHARED_LIB = Path(__file__).resolve().parents[1] / "lib"
if str(_SHARED_LIB) not in sys.path:
    sys.path.insert(0, str(_SHARED_LIB))

from session_role import read_role  # noqa: E402


_ENV_OVERRIDE = "SHIPWRIGHT_SECONDARY_PUSH_AUTH"


def _decide(project_root: Path) -> tuple[int, dict[str, str]]:
    """Return (exit_code, payload_for_json_output)."""
    marker = read_role(project_root)
    if marker is None:
        return 0, {
            "decision": "allow",
            "reason": "no_marker",
            "detail": (
                "No iterate_session_role.json — single-session default "
                "permissive."
            ),
        }
    role = marker.get("role")
    if role == "canonical":
        return 0, {
            "decision": "allow",
            "reason": "canonical",
            "detail": "Session is canonical for this repo.",
        }
    # Role is "secondary" by VALID_ROLES filter inside read_role.
    if os.environ.get(_ENV_OVERRIDE) == "1":
        return 0, {
            "decision": "allow",
            "reason": "secondary_with_override",
            "detail": (
                f"{_ENV_OVERRIDE}=1 set — secondary push explicitly "
                "authorised."
            ),
        }
    return 1, {
        "decision": "block",
        "reason": "secondary_no_override",
        "detail": (
            "Session is marked secondary. Canonical session pushes for "
            "this repo. To override (one-shot), set "
            f"{_ENV_OVERRIDE}=1 in the env, then re-run the push. To "
            "permanently flip roles, edit "
            ".shipwright/iterate_session_role.json or use "
            "session_role.write_role()."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Pre-push guard for parallel-iterate sessions.",
    )
    parser.add_argument(
        "--project-root",
        default=".",
        help="Path to the project root (defaults to cwd).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit structured JSON to stdout (decision, reason, detail).",
    )
    args = parser.parse_args(argv)

    project_root = Path(args.project_root).resolve()
    exit_code, payload = _decide(project_root)

    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        if exit_code == 0:
            print(f"check_session_role: ALLOW ({payload['reason']})")
            print(payload["detail"], file=sys.stderr)
        else:
            print(f"check_session_role: BLOCK ({payload['reason']})")
            print(payload["detail"], file=sys.stderr)

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
