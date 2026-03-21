#!/usr/bin/env python3
"""Capture session_id and plugin_root for /shipwright-design."""

from __future__ import annotations

import json
import os
import sys


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
