#!/usr/bin/env python3
"""CLI for the review-scratch private-path resolver — see
``scripts.lib.review_scratch`` for the mechanism and the bug it closes.

Usage:
    uv run review_scratch.py resolve --run-id <run_id> --name <name>
    uv run review_scratch.py cleanup --run-id <run_id>

``resolve`` prints the absolute path with forward slashes (Git-Bash and
native Python both accept that form in a redirect / CLI argument), so a
skill's bash step can capture it with plain command substitution:

    DIFF="$(uv run shared/scripts/tools/review_scratch.py resolve \\
        --run-id "$run_id" --name shipwright-review-diff.txt)"
    git diff HEAD > "$DIFF"
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # shared/

from scripts.lib.review_scratch import ReviewScratchError, cleanup, resolve  # noqa: E402


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    resolve_p = sub.add_parser("resolve", help="print the resolved scratch path")
    resolve_p.add_argument("--run-id", required=True)
    resolve_p.add_argument("--name", required=True)

    cleanup_p = sub.add_parser("cleanup", help="remove this run's scratch directory")
    cleanup_p.add_argument("--run-id", required=True)

    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if args.command == "resolve":
            path = resolve(args.run_id, args.name)
            print(path.as_posix())
        else:
            cleanup(args.run_id)
    except ReviewScratchError as exc:
        print(f"review_scratch: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
