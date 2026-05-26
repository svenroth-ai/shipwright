"""CLI argument parsing for `python -m shared.scripts.dev_server` /
`uv run shared/scripts/dev_server.py`.

Extracted from `shared/scripts/dev_server.py` during B4 split (campaign
`2026-05-25-bloat-cleanup-B-shipwright`). The argument surface
(start/stop/status, --cwd, --profile, --services-json) is preserved
verbatim — pre/post-split `--help` output is identical.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .multiservice import cmd_start, cmd_start_with_services, cmd_status, cmd_stop
from .profile_config import _normalize_service_entry
from .validation import _validate_services


def main_with_args(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Manage target project dev server(s)")
    parser.add_argument("action", choices=["start", "stop", "status"])
    parser.add_argument("--cwd", required=True, help="Target project directory")
    parser.add_argument(
        "--profile",
        help="Stack profile name (e.g., supabase-nextjs, vite-hono)",
    )
    parser.add_argument(
        "--services-json",
        help="Inline services JSON array; takes precedence over --profile",
    )
    args = parser.parse_args(argv)

    cwd = Path(args.cwd).resolve()
    if not cwd.is_dir():
        print(json.dumps({"error": f"directory not found: {cwd}"}, indent=2))
        return 1

    if args.action == "start":
        if args.services_json:
            if args.profile:
                print(
                    "[dev_server] --services-json overrides --profile",
                    file=sys.stderr,
                )
            try:
                raw = json.loads(args.services_json)
            except json.JSONDecodeError as e:
                print(
                    json.dumps(
                        {"running": False, "error": f"invalid --services-json: {e}"},
                        indent=2,
                    )
                )
                return 2
            if not isinstance(raw, list):
                print(
                    json.dumps(
                        {"running": False, "error": "--services-json must be a JSON array"},
                        indent=2,
                    )
                )
                return 2
            try:
                services = [_normalize_service_entry(e) for e in raw]
            except (TypeError, AttributeError) as e:
                print(
                    json.dumps(
                        {"running": False, "error": f"invalid services entry: {e}"},
                        indent=2,
                    )
                )
                return 2
            try:
                _validate_services(services)
            except ValueError as e:
                print(json.dumps({"running": False, "error": str(e)}, indent=2))
                return 2
            result = cmd_start_with_services(cwd, services, profile=None)
        else:
            result = cmd_start(cwd, args.profile)
    elif args.action == "stop":
        result = cmd_stop(cwd)
    else:
        result = cmd_status(cwd)

    print(json.dumps(result, indent=2))
    return 0 if result.get("error") is None else 1


def main() -> int:
    return main_with_args(sys.argv[1:])
