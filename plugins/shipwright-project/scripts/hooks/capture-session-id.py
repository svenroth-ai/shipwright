#!/usr/bin/env python3
"""Capture session_id and plugin_root, expose via Claude's context.

Adapted from deep-project. Renames:
- DEEP_SESSION_ID → SHIPWRIGHT_SESSION_ID
- DEEP_PLUGIN_ROOT → SHIPWRIGHT_PLUGIN_ROOT
"""

from __future__ import annotations

import json
import os
import sys


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, Exception):
        return 0  # Hooks should never fail

    session_id = payload.get("session_id")
    plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT", "")

    if not session_id:
        return 0

    context_parts = []

    existing_session_id = os.environ.get("SHIPWRIGHT_SESSION_ID")
    if existing_session_id != session_id:
        context_parts.append(f"SHIPWRIGHT_SESSION_ID={session_id}")

    if plugin_root:
        context_parts.append(f"SHIPWRIGHT_PLUGIN_ROOT={plugin_root}")

    if context_parts:
        output = {
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": "\n".join(context_parts),
            }
        }
        print(json.dumps(output))

    # Also try CLAUDE_ENV_FILE for bash commands (fallback)
    env_file = os.environ.get("CLAUDE_ENV_FILE")
    if env_file:
        try:
            existing_content = ""
            try:
                with open(env_file) as f:
                    existing_content = f.read()
            except FileNotFoundError:
                pass

            lines_to_write = []
            if f"SHIPWRIGHT_SESSION_ID={session_id}" not in existing_content:
                lines_to_write.append(f"export SHIPWRIGHT_SESSION_ID={session_id}\n")

            if lines_to_write:
                with open(env_file, "a") as f:
                    f.writelines(lines_to_write)
        except OSError:
            pass

    return 0


if __name__ == "__main__":
    sys.exit(main())
