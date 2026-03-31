#!/usr/bin/env python3
"""PostToolUse hook: Increment tool call counter.

Atomically increments .shipwright_toolcall_count in the project root
(via SHIPWRIGHT_PROJECT_ROOT env var, fallback to cwd).
Used by estimate_context_pressure.py to detect when context window
is getting full.

Usage (from hooks.json):
    uv run ${CLAUDE_PLUGIN_ROOT}/../../shared/scripts/hooks/track_tool_calls.py
"""

import json
import os
import sys
from pathlib import Path


def _resolve_project_root() -> Path:
    """Resolve project root from SHIPWRIGHT_PROJECT_ROOT env var, fallback to cwd."""
    env_root = os.environ.get("SHIPWRIGHT_PROJECT_ROOT")
    if env_root:
        return Path(env_root)
    return Path.cwd()


def main() -> int:
    # Consume stdin (hook protocol)
    try:
        json.load(sys.stdin)
    except Exception:
        pass

    counter_file = _resolve_project_root() / ".shipwright_toolcall_count"

    count = 0
    if counter_file.exists():
        try:
            count = int(counter_file.read_text(encoding="utf-8").strip())
        except (ValueError, OSError):
            count = 0

    count += 1
    counter_file.write_text(str(count), encoding="utf-8")

    return 0


if __name__ == "__main__":
    sys.exit(main())
