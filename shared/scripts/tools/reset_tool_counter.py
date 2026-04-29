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
        project_root = Path(os.environ.get("SHIPWRIGHT_PROJECT_ROOT", Path.cwd()))
        counter_file = project_root / counter_file

    counter_file.parent.mkdir(parents=True, exist_ok=True)
    counter_file.write_text("0", encoding="utf-8")

    print(json.dumps({"reset": True, "counter_file": str(counter_file)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
