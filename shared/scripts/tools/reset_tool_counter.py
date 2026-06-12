#!/usr/bin/env python3
"""Reset the tool call counter to zero.

Used by the orchestrator between sections in autonomous mode
to prevent stale counter values from triggering false checkpoints.

Usage:
    uv run reset_tool_counter.py [--counter-file <path>]

Output (JSON):
    {"reset": true, "counter_file": "/path/to/.shipwright/toolcall_count"}
"""

import argparse
import json
import os
import sys
from pathlib import Path


def _resolve_project_root() -> Path:
    """Resolve the project root the SAME way the producer (track_tool_calls)
    does — via ``resolve_project_root()`` auto-descent (F10). Falls back to
    ``SHIPWRIGHT_PROJECT_ROOT`` / cwd when the shared resolver is unavailable."""
    try:
        shared_scripts = str(Path(__file__).resolve().parent.parent)
        if shared_scripts not in sys.path:
            sys.path.insert(0, shared_scripts)
        from lib.project_root import resolve_project_root  # noqa: PLC0415

        return resolve_project_root()
    except (ImportError, ValueError):
        env_root = os.environ.get("SHIPWRIGHT_PROJECT_ROOT")
        return Path(env_root) if env_root else Path.cwd()


def main() -> int:
    parser = argparse.ArgumentParser(description="Reset tool call counter")
    parser.add_argument(
        "--counter-file",
        default=".shipwright/toolcall_count",
        help="Path to tool call counter file (default: .shipwright/toolcall_count in cwd)",
    )
    args = parser.parse_args()

    counter_file = Path(args.counter_file)
    if not counter_file.is_absolute():
        counter_file = _resolve_project_root() / counter_file

    counter_file.parent.mkdir(parents=True, exist_ok=True)
    counter_file.write_text("0", encoding="utf-8")

    print(json.dumps({"reset": True, "counter_file": str(counter_file)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
