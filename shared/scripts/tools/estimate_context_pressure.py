#!/usr/bin/env python3
"""Estimate context window pressure from tool call count.

Reads .shipwright/toolcall_count (plain integer file) and returns
a recommendation on whether to checkpoint.

Usage:
    uv run estimate_context_pressure.py [--counter-file <path>] [--threshold <n>] [--mode <mode>]

Modes:
    builder (default): threshold 120 — used within /shipwright-build (guided mode)
    orchestrator:      threshold 300 — used by /shipwright-run when delegating to subagents

Output (JSON):
    {"tool_calls": 142, "threshold": 120, "recommend_checkpoint": true, "mode": "builder"}
"""

import argparse
import json
import os
import sys
from pathlib import Path


MODE_THRESHOLDS = {
    "builder": 120,
    "orchestrator": 300,
}


def _resolve_project_root() -> Path:
    """Resolve the project root the SAME way the producer (track_tool_calls)
    does — via ``resolve_project_root()``, which auto-descends into a managed
    subdirectory.

    F10: the readers previously used ``os.environ/Path.cwd()`` only, so in an
    auto-descent layout the producer incremented ``<subdir>/.shipwright/…`` while
    the reader looked at ``<workspace>/.shipwright/…`` (never created) → count 0
    → context-pressure checkpointing silently dead.
    """
    try:
        shared_scripts = str(Path(__file__).resolve().parent.parent)
        if shared_scripts not in sys.path:
            sys.path.insert(0, shared_scripts)
        from lib.project_root import resolve_project_root  # noqa: PLC0415

        return resolve_project_root()
    except (ImportError, ValueError):
        env_root = os.environ.get("SHIPWRIGHT_PROJECT_ROOT")
        return Path(env_root) if env_root else Path.cwd()


def estimate_pressure(counter_file: Path, threshold: int, mode: str = "builder") -> dict:
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
        "mode": mode,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Estimate context pressure")
    parser.add_argument(
        "--counter-file",
        default=".shipwright/toolcall_count",
        help="Path to tool call counter file (default: .shipwright/toolcall_count in cwd)",
    )
    parser.add_argument(
        "--threshold",
        type=int,
        default=None,
        help="Tool call threshold for checkpoint recommendation (default: mode-dependent)",
    )
    parser.add_argument(
        "--mode",
        choices=list(MODE_THRESHOLDS.keys()),
        default="builder",
        help="Execution mode: 'builder' (120, default) or 'orchestrator' (300)",
    )
    args = parser.parse_args()

    threshold = args.threshold if args.threshold is not None else MODE_THRESHOLDS[args.mode]

    counter_file = Path(args.counter_file)
    if not counter_file.is_absolute():
        counter_file = _resolve_project_root() / counter_file

    result = estimate_pressure(counter_file, threshold, args.mode)
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
