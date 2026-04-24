#!/usr/bin/env python3
"""Write shipwright_run_config.json for a new project.

Called by the shipwright-project plugin's intro gate when the user picks
"Full Pipeline" and no run_config exists yet.

Detects the stack profile from package.json (simple heuristic: presence of
'next' dep -> supabase-nextjs). Errors clearly if no detectable stack.

Usage:
    uv run write_run_config.py --project-root /path/to/project
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


def detect_profile(project_root: Path) -> str | None:
    """Detect stack profile from package.json deps. Returns profile name or None."""
    pkg = project_root / "package.json"
    if not pkg.exists():
        return None
    try:
        data = json.loads(pkg.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
    if "next" in deps:
        return "supabase-nextjs"
    return None


def write_run_config(project_root: Path, profile: str) -> Path:
    """Write shipwright_run_config.json with initial state."""
    config_path = project_root / "shipwright_run_config.json"
    if config_path.exists():
        raise FileExistsError(f"shipwright_run_config.json already exists at {config_path}")
    now = datetime.now(timezone.utc).isoformat()
    config = {
        "contractVersion": 1,
        "pipeline": ["project", "design", "plan", "build", "test", "changelog", "deploy", "compliance"],
        "status": "pending",
        "current_step": "project",
        "completed_steps": [],
        "profile": profile,
        "standalone": False,
        "created_at": now,
        "updated_at": now,
    }
    config_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    return config_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Write shipwright_run_config.json for a new project")
    parser.add_argument("--project-root", required=True, type=Path)
    parser.add_argument("--profile", type=str, help="Override auto-detected profile")
    args = parser.parse_args()

    project_root: Path = args.project_root.resolve()
    if not project_root.is_dir():
        print(f"ERROR: not a directory: {project_root}", file=sys.stderr)
        return 1

    profile = args.profile or detect_profile(project_root)
    if not profile:
        print(
            "ERROR: could not detect stack profile from package.json. "
            "Pass --profile explicitly (e.g., --profile supabase-nextjs).",
            file=sys.stderr,
        )
        return 2

    try:
        config_path = write_run_config(project_root, profile)
    except FileExistsError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 3

    print(f"Wrote {config_path} with profile={profile}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
