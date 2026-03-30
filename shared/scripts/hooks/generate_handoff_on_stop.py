#!/usr/bin/env python3
"""Stop hook: Generate session_handoff.md before session ends.

Automatically generates agent_docs/session_handoff.md from current
project state (configs, git, decision log). Non-blocking (exit 0).

Usage (from hooks.json):
    uv run ${CLAUDE_PLUGIN_ROOT}/../../shared/scripts/hooks/generate_handoff_on_stop.py
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def main() -> int:
    # Consume stdin (hook protocol)
    try:
        json.load(sys.stdin)
    except Exception:
        pass

    project_root = Path.cwd()

    # Guard: skip if not in a shipwright-managed project
    has_run_config = (project_root / "shipwright_run_config.json").exists()
    has_agent_docs = (project_root / "agent_docs").is_dir()
    if not has_run_config and not has_agent_docs:
        return 0

    try:
        # Import the shared generator
        scripts_dir = Path(__file__).resolve().parent.parent
        sys.path.insert(0, str(scripts_dir))
        from tools.generate_session_handoff import generate_handoff

        session_id = os.environ.get("SHIPWRIGHT_SESSION_ID", "unknown")
        content = generate_handoff(project_root, session_id, reason="session end")

        agent_docs = project_root / "agent_docs"
        agent_docs.mkdir(exist_ok=True)
        (agent_docs / "session_handoff.md").write_text(content, encoding="utf-8")

        # Update build dashboard with "paused" status if build is active
        try:
            from tools.update_build_dashboard import generate_dashboard
            from lib.config import read_config

            build_config = read_config("build", project_root)
            if build_config.get("sections"):
                dashboard = generate_dashboard(
                    project_root, status="paused", session_id=session_id,
                )
                (agent_docs / "build_dashboard.md").write_text(dashboard, encoding="utf-8")
        except Exception:
            pass  # Dashboard update is best-effort

        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "Stop",
                "additionalContext": "Session handoff generated at agent_docs/session_handoff.md",
            }
        }))
    except Exception as e:
        # Never block session end — report failure as info
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "Stop",
                "additionalContext": f"Session handoff generation skipped: {e}",
            }
        }))

    return 0


if __name__ == "__main__":
    sys.exit(main())
