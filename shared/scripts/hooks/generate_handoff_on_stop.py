#!/usr/bin/env python3
"""Stop hook: Generate session_handoff.md + update dashboard + fallback phase-completion.

Automatically generates agent_docs/session_handoff.md from current
project state (configs, git, decision log). Non-blocking (exit 0).

Also detects if a phase completed but wasn't marked in the orchestrator
config (e.g., standalone /shipwright-build without /shipwright-run), and
triggers the compliance update as a fallback.

Usage (from hooks.json):
    uv run ${CLAUDE_PLUGIN_ROOT}/../../shared/scripts/hooks/generate_handoff_on_stop.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def _detect_phase_complete(current_step: str, project_root: Path, completed_steps: set) -> bool:
    """Check if current phase has completed work but isn't marked complete."""
    if current_step in completed_steps:
        return False

    if current_step == "build":
        config_path = project_root / "shipwright_build_config.json"
        if config_path.exists():
            try:
                config = json.loads(config_path.read_text(encoding="utf-8"))
                sections = config.get("sections", [])
                return bool(sections) and all(
                    s.get("status") == "complete" for s in sections
                )
            except (json.JSONDecodeError, OSError):
                pass
    elif current_step == "plan":
        config_path = project_root / "shipwright_plan_config.json"
        if config_path.exists():
            try:
                config = json.loads(config_path.read_text(encoding="utf-8"))
                return config.get("status") == "complete"
            except (json.JSONDecodeError, OSError):
                pass
    elif current_step == "project":
        config_path = project_root / "shipwright_project_config.json"
        if config_path.exists():
            try:
                config = json.loads(config_path.read_text(encoding="utf-8"))
                return config.get("status") == "complete"
            except (json.JSONDecodeError, OSError):
                pass

    return False


def _run_phase_completion(project_root: Path, step: str) -> None:
    """Mark phase complete in orchestrator config (triggers compliance update)."""
    # Find orchestrator script (sibling plugin)
    scripts_dir = Path(__file__).resolve().parent.parent
    # shared/scripts/hooks -> shared -> plugins/shipwright-run
    orchestrator = scripts_dir.parent.parent / "plugins" / "shipwright-run" / "scripts" / "lib" / "orchestrator.py"

    if not orchestrator.exists():
        return

    try:
        subprocess.run(
            [sys.executable, str(orchestrator),
             "update-step", "--project-root", str(project_root),
             "--step", step, "--status", "complete"],
            capture_output=True, timeout=30,
        )
    except (subprocess.TimeoutExpired, OSError):
        pass


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

        # Update build dashboard with "paused" status
        try:
            from tools.update_build_dashboard import generate_dashboard

            dashboard = generate_dashboard(
                project_root, status="paused", session_id=session_id,
            )
            (agent_docs / "build_dashboard.md").write_text(dashboard, encoding="utf-8")
        except Exception:
            pass  # Dashboard update is best-effort

        # Fallback: detect incomplete phase-completion and trigger it
        try:
            run_config_path = project_root / "shipwright_run_config.json"
            if run_config_path.exists():
                run_config = json.loads(run_config_path.read_text(encoding="utf-8"))
                current_step = run_config.get("current_step")
                completed_steps = set(run_config.get("completed_steps", []))

                if current_step and _detect_phase_complete(current_step, project_root, completed_steps):
                    _run_phase_completion(project_root, current_step)
        except Exception:
            pass  # Phase-completion fallback is best-effort

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
