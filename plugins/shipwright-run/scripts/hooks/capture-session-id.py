#!/usr/bin/env python3
"""Capture session_id and plugin_root for /shipwright-run."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def _resolve_root() -> str:
    """Find the Shipwright project root, tolerating subdirectory layouts."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "shared" / "scripts"))
    try:
        from lib.project_root import resolve_project_root
        return str(resolve_project_root())
    except (ImportError, ValueError):
        return os.getcwd()


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, Exception):
        return 0

    session_id = payload.get("session_id")
    plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT", "")

    if not session_id:
        return 0

    context_parts = []
    if os.environ.get("SHIPWRIGHT_SESSION_ID") != session_id:
        context_parts.append(f"SHIPWRIGHT_SESSION_ID={session_id}")
    if plugin_root:
        context_parts.append(f"SHIPWRIGHT_PLUGIN_ROOT={plugin_root}")

    context_parts.append(f"SHIPWRIGHT_PROJECT_ROOT={_resolve_root()}")

    root_sid = os.environ.get("SHIPWRIGHT_ROOT_SESSION_ID")
    if root_sid:
        context_parts.append(f"SHIPWRIGHT_ROOT_SESSION_ID={root_sid}")
    loop_id = os.environ.get("SHIPWRIGHT_LOOP_ID")
    if loop_id:
        context_parts.append(f"SHIPWRIGHT_LOOP_ID={loop_id}")
    loop_unit = os.environ.get("SHIPWRIGHT_LOOP_UNIT_ID")
    if loop_unit:
        context_parts.append(f"SHIPWRIGHT_LOOP_UNIT_ID={loop_unit}")

    if context_parts:
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": "\n".join(context_parts),
            }
        }))

    return 0


if __name__ == "__main__":
    sys.exit(main())
