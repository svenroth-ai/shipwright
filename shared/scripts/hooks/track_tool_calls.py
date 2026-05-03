#!/usr/bin/env python3
"""PostToolUse hook: Increment tool call counter.

Atomically increments .shipwright/toolcall_count in the project root
(via SHIPWRIGHT_PROJECT_ROOT env var, fallback to cwd).
Used by estimate_context_pressure.py to detect when context window
is getting full.

Usage (from hooks.json):
    uv run "${CLAUDE_PLUGIN_ROOT}/../../shared/scripts/hooks/track_tool_calls.py"
"""

import json
import os
import sys
from pathlib import Path


def _resolve_project_root() -> Path:
    """Resolve project root via shared resolver, fallback to env/cwd."""
    try:
        scripts_dir = str(Path(__file__).resolve().parent.parent)
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)
        from lib.project_root import resolve_project_root
        return resolve_project_root()
    except (ImportError, ValueError):
        env_root = os.environ.get("SHIPWRIGHT_PROJECT_ROOT")
        if env_root:
            return Path(env_root)
        return Path.cwd()


def _is_shipwright_project(root: Path) -> bool:
    """Check if the directory is an active Shipwright project."""
    markers = ["shipwright_run_config.json", "shipwright_build_config.json"]
    return any((root / m).exists() for m in markers)


def main() -> int:
    # Consume stdin (hook protocol)
    try:
        json.load(sys.stdin)
    except Exception:
        pass

    project_root = _resolve_project_root()

    # Only track in actual Shipwright projects
    if not _is_shipwright_project(project_root):
        return 0

    counter_file = project_root / ".shipwright" / "toolcall_count"

    count = 0
    if counter_file.exists():
        try:
            count = int(counter_file.read_text(encoding="utf-8").strip())
        except (ValueError, OSError):
            count = 0

    count += 1
    counter_file.parent.mkdir(parents=True, exist_ok=True)
    counter_file.write_text(str(count), encoding="utf-8")

    return 0


if __name__ == "__main__":
    sys.exit(main())
