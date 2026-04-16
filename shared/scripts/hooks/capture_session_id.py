#!/usr/bin/env python3
"""Canonical SessionStart hook for all Shipwright plugins.

Injects Shipwright environment variables into Claude's session context:
- SHIPWRIGHT_SESSION_ID: current session id (from hook payload)
- SHIPWRIGHT_PLUGIN_ROOT: active plugin directory (from CLAUDE_PLUGIN_ROOT)
- SHIPWRIGHT_PROJECT_ROOT: resolved via resolve_project_root() for
  subdirectory-safe monorepo support. Falls back to cwd on failure.
- SHIPWRIGHT_ROOT_SESSION_ID / SHIPWRIGHT_LOOP_ID / SHIPWRIGHT_LOOP_UNIT_ID:
  autonomous-loop env vars, only emitted when set by the parent runner.

Also writes SHIPWRIGHT_SESSION_ID into CLAUDE_ENV_FILE (if provided) so
bash subprocesses inherit it — additionalContext alone does not reach
child processes spawned by Claude's Bash tool.

This replaces the 8 per-plugin copies that used to live in
plugins/*/scripts/hooks/capture-session-id.py. All plugin hooks.json
files now reference this single canonical implementation.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# Make shared lib importable regardless of which plugin invokes this hook.
# This file lives at shared/scripts/hooks/, so parents[1] is shared/scripts/
_SHARED_SCRIPTS = Path(__file__).resolve().parents[1]
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))


def _resolve_root() -> str:
    """Find the Shipwright project root, tolerating subdirectory layouts."""
    try:
        from lib.project_root import resolve_project_root
        return str(resolve_project_root())
    except (ImportError, ValueError):
        return os.getcwd()


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, Exception):
        return 0  # Hooks should never fail

    session_id = payload.get("session_id")
    plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT", "")

    if not session_id:
        return 0

    context_parts: list[str] = []

    if os.environ.get("SHIPWRIGHT_SESSION_ID") != session_id:
        context_parts.append(f"SHIPWRIGHT_SESSION_ID={session_id}")

    if plugin_root:
        context_parts.append(f"SHIPWRIGHT_PLUGIN_ROOT={plugin_root}")

    context_parts.append(f"SHIPWRIGHT_PROJECT_ROOT={_resolve_root()}")

    # Autonomous-loop propagation (only emitted when parent runner set them).
    for var in (
        "SHIPWRIGHT_ROOT_SESSION_ID",
        "SHIPWRIGHT_LOOP_ID",
        "SHIPWRIGHT_LOOP_UNIT_ID",
    ):
        value = os.environ.get(var)
        if value:
            context_parts.append(f"{var}={value}")

    if context_parts:
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": "\n".join(context_parts),
            }
        }))

    # CLAUDE_ENV_FILE fallback so SHIPWRIGHT_SESSION_ID reaches bash subprocesses.
    env_file = os.environ.get("CLAUDE_ENV_FILE")
    if env_file:
        try:
            existing = ""
            try:
                with open(env_file, encoding="utf-8") as f:
                    existing = f.read()
            except FileNotFoundError:
                pass
            if f"SHIPWRIGHT_SESSION_ID={session_id}" not in existing:
                with open(env_file, "a", encoding="utf-8") as f:
                    f.write(f"export SHIPWRIGHT_SESSION_ID={session_id}\n")
        except OSError:
            pass

    return 0


if __name__ == "__main__":
    sys.exit(main())
