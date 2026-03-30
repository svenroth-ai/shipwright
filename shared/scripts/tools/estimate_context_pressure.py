#!/usr/bin/env python3
"""Estimate context window pressure from tool call count.

Reads .shipwright_toolcall_count (plain integer file) and returns
a recommendation on whether to checkpoint.

Usage:
    uv run estimate_context_pressure.py [--counter-file <path>] [--threshold <n>]

Output (JSON):
    {"tool_calls": 142, "threshold": 120, "recommend_checkpoint": true}
"""

import argparse
import json
import sys
from pathlib import Path


def estimate_pressure(counter_file: Path, threshold: int) -> dict:
    """Read counter file and compute pressure recommendation."""
    tool_calls = 0
    if counter_file.exists():
        try:
            tool_calls = int(counter_file.read_text(encoding="utf-8").strip())
        except (ValueError, OSError):
            tool_calls = 0

    return {
        "tool_calls": tool_calls,
        "threshold": threshold,
        "recommend_checkpoint": tool_calls >= threshold,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Estimate context pressure")
    parser.add_argument(
        "--counter-file",
        default=".shipwright_toolcall_count",
        help="Path to tool call counter file (default: .shipwright_toolcall_count in cwd)",
    )
    parser.add_argument(
        "--threshold",
        type=int,
        default=120,
        help="Tool call threshold for checkpoint recommendation (default: 120)",
    )
    args = parser.parse_args()

    counter_file = Path(args.counter_file)
    if not counter_file.is_absolute():
        counter_file = Path.cwd() / counter_file

    result = estimate_pressure(counter_file, args.threshold)
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
