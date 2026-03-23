#!/usr/bin/env python3
"""Orchestrator for shipwright-run.

Manages pipeline state: which skill runs next, progress tracking, resume support.

Usage:
    uv run orchestrator.py write-config --scope <scope> --profile <profile> --autonomy <level>
    uv run orchestrator.py get-next-step --project-root <path>
    uv run orchestrator.py update-step --project-root <path> --step <step> --status <status>

Output (JSON): config or next step info
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


CONFIG_NAME = "shipwright_run_config.json"

PIPELINE_STEPS = ["project", "design", "plan", "build", "test", "deploy", "changelog"]


def load_run_config(project_root: Path) -> dict[str, Any]:
    """Load orchestrator config."""
    path = project_root / CONFIG_NAME
    if not path.exists():
        return {}  # Valid: first run, no config yet
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(json.dumps({
            "warning": "Corrupt orchestrator config",
            "error_category": "validation",
            "what_failed": f"Parse {CONFIG_NAME}",
            "exception": str(exc),
            "alternative": "Delete the file and re-run /shipwright-run to recreate",
        }), file=sys.stderr)
        return {}


def save_run_config(project_root: Path, config: dict[str, Any]) -> None:
    """Save orchestrator config."""
    path = project_root / CONFIG_NAME
    config["updated_at"] = datetime.now(timezone.utc).isoformat()
    path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")


def create_config(
    scope: str,
    profile: Optional[str],
    autonomy: str,
    deploy_target: str,
    project_root: Path,
) -> dict[str, Any]:
    """Create initial orchestrator config."""
    config = {
        "scope": scope,
        "profile": profile,
        "autonomy": autonomy,
        "deploy_target": deploy_target,
        "pipeline": PIPELINE_STEPS.copy(),
        "status": "in_progress",
        "current_step": "project",
        "completed_steps": [],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    save_run_config(project_root, config)
    return config


def get_next_step(project_root: Path) -> dict[str, Any]:
    """Determine what the next pipeline step should be."""
    config = load_run_config(project_root)

    if not config:
        return {"next_step": "project", "reason": "no config found, start from beginning"}

    completed = set(config.get("completed_steps", []))
    pipeline = config.get("pipeline", PIPELINE_STEPS)

    for step in pipeline:
        if step not in completed:
            return {
                "next_step": step,
                "completed": list(completed),
                "remaining": [s for s in pipeline if s not in completed],
                "scope": config.get("scope"),
                "profile": config.get("profile"),
                "autonomy": config.get("autonomy"),
            }

    return {
        "next_step": None,
        "reason": "all steps completed",
        "completed": list(completed),
    }


def update_step(project_root: Path, step: str, status: str) -> dict[str, Any]:
    """Update a pipeline step's status."""
    config = load_run_config(project_root)

    if status == "complete":
        completed = config.get("completed_steps", [])
        if step not in completed:
            completed.append(step)
        config["completed_steps"] = completed

        # Set next step
        pipeline = config.get("pipeline", PIPELINE_STEPS)
        remaining = [s for s in pipeline if s not in completed]
        config["current_step"] = remaining[0] if remaining else None
        if not remaining:
            config["status"] = "complete"

    elif status == "in_progress":
        config["current_step"] = step

    elif status == "failed":
        config["current_step"] = step
        config["status"] = "failed"

    save_run_config(project_root, config)
    return config


def main() -> int:
    parser = argparse.ArgumentParser(description="Orchestrator")
    subparsers = parser.add_subparsers(dest="command", required=True)

    p = subparsers.add_parser("write-config")
    p.add_argument("--scope", required=True, choices=["full_app", "extension", "iterate"])
    p.add_argument("--profile", default=None)
    p.add_argument("--autonomy", default="guided", choices=["guided", "autonomous"])
    p.add_argument("--deploy-target", default="jelastic-dev")
    p.add_argument("--project-root", default=".")

    p = subparsers.add_parser("get-next-step")
    p.add_argument("--project-root", default=".")

    p = subparsers.add_parser("update-step")
    p.add_argument("--project-root", default=".")
    p.add_argument("--step", required=True, choices=PIPELINE_STEPS)
    p.add_argument("--status", required=True, choices=["in_progress", "complete", "failed"])

    args = parser.parse_args()
    project_root = Path(args.project_root).resolve()

    if args.command == "write-config":
        config = create_config(
            args.scope, args.profile, args.autonomy,
            args.deploy_target, project_root,
        )
        print(json.dumps(config, indent=2))

    elif args.command == "get-next-step":
        result = get_next_step(project_root)
        print(json.dumps(result, indent=2))

    elif args.command == "update-step":
        config = update_step(project_root, args.step, args.status)
        print(json.dumps(config, indent=2))

    return 0


if __name__ == "__main__":
    sys.exit(main())
