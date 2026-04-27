#!/usr/bin/env python3
"""Write shipwright_project_config.json after scaffolding.

New Shipwright script (not from upstream).

Usage:
    uv run write-project-config.py --planning-dir <path> --profile <name> --scope <scope>

Output (JSON): the written config
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from lib.state import detect_state


def main() -> int:
    parser = argparse.ArgumentParser(description="Write shipwright project config")
    parser.add_argument("--planning-dir", required=True, help="Path to planning directory")
    parser.add_argument("--profile", required=True, help="Profile name (e.g., supabase-nextjs)")
    parser.add_argument("--scope", required=True, choices=["full_app", "extension"], help="Project scope")
    parser.add_argument("--project-root", help="Project root (defaults to parent of planning-dir)")
    parser.add_argument("--status", default="complete", choices=["in_progress", "complete"],
                        help="Config status (default: complete)")
    args = parser.parse_args()

    planning_dir = Path(args.planning_dir).resolve()
    project_root = Path(args.project_root).resolve() if args.project_root else planning_dir.parent

    if args.status == "in_progress":
        # Early config: minimal tracking before scaffolding completes
        config = {
            "status": "in_progress",
            "scope": args.scope,
            "profile": args.profile,
        }
    else:
        # Full config: after scaffolding with splits and artifacts
        state = detect_state(planning_dir)
        config = {
            "status": "complete",
            "scope": args.scope,
            "profile": args.profile,
            "planning_dir": str(planning_dir.relative_to(project_root)),
            "splits": [
                {"name": s, "status": "not_started"}
                for s in state["splits"]
            ],
            "artifacts": {
                "claude_md": (project_root / "CLAUDE.md").exists(),
                "agent_docs": (project_root / ".shipwright" / "agent_docs").is_dir(),  # artifact-path-canon: legacy
                "manifest": state["manifest_created"],
            },
        }

    config_path = project_root / "shipwright_project_config.json"
    config_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")

    print(json.dumps(config, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
