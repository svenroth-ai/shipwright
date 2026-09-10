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
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _build_v1_style_phase_task_seed(now: str) -> dict[str, Any]:
    """A full-shape ``phase_tasks[]`` "project" entry, ``awaiting_launch``.

    Mirrors ``plugins/shipwright-run/scripts/lib/orchestrator_pkg/
    config_factory.py``'s ``build_v1_phase_task`` field-for-field (not
    imported: that would be the ADR-045 cross-plugin ``lib``-namespace
    collision — this plugin and ``shipwright-run`` each resolve their own
    ``lib`` package, and `create_config`'s own docstring documents the same
    tradeoff for the reverse direction). External code review, sub-iterate
    s5 (this campaign): a bare ``{"phase": ..., "splitId": ..., "status":
    ...}`` literal omits every field ``run_config.v2.schema.json``'s
    ``PhaseTask.required`` mandates (``phaseTaskId``, ``sessionUuid``,
    ``version``, ``title``, ``slashCommand``, ``prerequisites``,
    ``executionCount``, ``createdAt``) — and since ``_upsert_v1_phase_task``
    only ever mutates ``status``/``startedAt``/``completedAt`` on a match, an
    incomplete seed here stays incomplete for the life of the run, unlike
    every other ``phase_tasks[]`` producer this campaign's writers use.
    """
    return {
        "phaseTaskId": "ptk-" + uuid.uuid4().hex[:8],
        "phase": "project",
        "splitId": None,
        "sessionUuid": str(uuid.uuid4()),
        "version": 1,
        "status": "awaiting_launch",
        "title": "project",
        "description": (
            "Advanced via the v1 update_step path (standalone / legacy / "
            "adopted run, no orchestrator session)."
        ),
        "slashCommand": "/shipwright-project",
        "prerequisites": [],
        "claimedBySessionUuid": None,
        "claimAttemptedAt": None,
        "executionCount": 0,
        "createdAt": now,
        "awaitingLaunchAt": None,
        "startedAt": None,
        "completedAt": None,
        "result": None,
        "errors": [],
    }


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
        # A full-shape v1-style phase_tasks[] seed for "project" — NOT just a
        # comment saying "the next writer creates it" (external code review,
        # OpenAI HIGH): the old current_step="project" this replaces was the
        # ONLY signal the Stop-hook phase-completion fallback had if Step 8's
        # explicit `update-step --status complete` call never ran (session
        # died first). Without a seed here, that fallback has nothing to key
        # on for a project created this way until the explicit call lands.
        # `_upsert_v1_phase_task` finds and updates this same entry in place
        # (matches on phase + splitId=None); campaign
        # p4-04-retire-write-once-steps, sub-iterate s5.
        "phase_tasks": [_build_v1_style_phase_task_seed(now)],
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
