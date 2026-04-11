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
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


# Add shared scripts and local lib to path for imports
_SHARED_SCRIPTS = Path(__file__).resolve().parent.parent.parent.parent.parent / "shared" / "scripts"
_LOCAL_LIB = str(Path(__file__).resolve().parent)
sys.path.insert(0, str(_SHARED_SCRIPTS))
if _LOCAL_LIB not in sys.path:
    sys.path.insert(0, _LOCAL_LIB)

CONFIG_NAME = "shipwright_run_config.json"

# Compliance plugin location (sibling plugin)
_THIS_PLUGIN = Path(__file__).parent.parent.parent
_COMPLIANCE_SCRIPT = _THIS_PLUGIN.parent / "shipwright-compliance" / "scripts" / "tools" / "update_compliance.py"

PIPELINE_STEPS = ["project", "design", "plan", "build", "test", "changelog", "compliance", "deploy"]

# Conditional steps: included only when their check function returns True
CONDITIONAL_STEPS = {
    "security": {
        "check_fn": "_check_security_available",
        "after": "test",  # inserted after this step
    },
}


def _check_security_available() -> bool:
    """Return True if any security scanner backend is configured."""
    # Explicit backend selection
    if os.environ.get("SHIPWRIGHT_SCANNER_BACKEND"):
        return True
    # Aikido (cloud)
    if os.environ.get("AIKIDO_CLIENT_ID"):
        return True
    # OSS tools (local)
    return any(shutil.which(t) for t in ("semgrep", "trivy", "gitleaks"))


_CHECK_FNS = {
    "_check_security_available": _check_security_available,
}


def build_pipeline() -> list[str]:
    """Build pipeline with conditional steps resolved."""
    pipeline = PIPELINE_STEPS.copy()
    for step, rule in CONDITIONAL_STEPS.items():
        check_fn = _CHECK_FNS.get(rule["check_fn"], lambda: False)
        if check_fn():
            after = rule["after"]
            idx = pipeline.index(after) + 1
            pipeline.insert(idx, step)
    return pipeline


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
    """Create initial orchestrator config.

    If a standalone config exists (from prior /shipwright-project or similar),
    merges its completed_steps so already-finished phases are not repeated.
    """
    pipeline = build_pipeline()

    # Merge: carry over completed_steps from standalone invocations
    existing = load_run_config(project_root)
    prior_completed: list[str] = []
    if existing.get("standalone") and existing.get("completed_steps"):
        # Only keep steps that exist in the new pipeline
        prior_completed = [s for s in existing["completed_steps"] if s in pipeline]

    # Determine starting step (first uncompleted pipeline step)
    remaining = [s for s in pipeline if s not in prior_completed]
    current_step = remaining[0] if remaining else None

    config = {
        "scope": scope,
        "profile": profile,
        "autonomy": autonomy,
        "deploy_target": deploy_target,
        "pipeline": pipeline,
        "status": "in_progress" if current_step else "complete",
        "current_step": current_step,
        "completed_steps": prior_completed,
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


def run_compliance_update(project_root: Path, phase: str) -> dict[str, Any] | None:
    """Run incremental compliance update after a phase completes.

    Returns parsed JSON output on success, None if compliance plugin not found
    or on error (non-blocking).
    """
    if not _COMPLIANCE_SCRIPT.exists():
        return None

    try:
        result = subprocess.run(
            [sys.executable, str(_COMPLIANCE_SCRIPT),
             "--project-root", str(project_root),
             "--phase", phase],
            capture_output=True, text=True, encoding="utf-8", timeout=30,
            cwd=str(project_root),
        )
        if result.returncode == 0 and result.stdout.strip():
            return json.loads(result.stdout)
        # Non-zero exit or empty stdout — log for diagnostics
        sys.stderr.write(json.dumps({
            "level": "warn",
            "message": f"Compliance update failed for phase '{phase}'",
            "returncode": result.returncode,
            "stderr": (result.stderr or "")[:500],
        }) + "\n")
    except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError) as exc:
        sys.stderr.write(json.dumps({
            "level": "warn",
            "message": f"Compliance update error for phase '{phase}'",
            "error": str(exc),
        }) + "\n")
    return None


def _reset_tool_counter(project_root: Path) -> None:
    """Reset tool call counter to zero (between-skill cleanup)."""
    counter = project_root / ".shipwright_toolcall_count"
    try:
        counter.write_text("0", encoding="utf-8")
    except OSError:
        pass


def update_step(project_root: Path, step: str, status: str, *, force: bool = False) -> dict[str, Any]:
    """Update a pipeline step's status.

    On completion, runs phase validation first (unless force=True or standalone).
    If validation returns ask-level issues, sets status to "needs_validation"
    and returns without marking complete. The caller (SKILL.md) should then
    ask the user and re-call with force=True if the user approves.

    On completion, also triggers incremental compliance update.
    """
    config = load_run_config(project_root)

    # Bootstrap: standalone invocation without /shipwright-run
    if not config:
        config = {
            "pipeline": build_pipeline(),
            "status": "in_progress",
            "current_step": step,
            "completed_steps": [],
            "standalone": True,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

    # Standalone configs skip interactive validation (no user to answer)
    is_standalone = config.get("standalone", False)

    if status == "complete":
        # Phase validation gate (skip for standalone — no interactive user)
        if not force and not is_standalone:
            from phase_validators import validate_phase
            valid, issues = validate_phase(step, project_root)
            ask_issues = [i for i in issues if i["severity"] == "ask"]
            inform_issues = [i for i in issues if i["severity"] == "inform"]

            # Record inform-level notes (non-blocking)
            if inform_issues:
                notes = config.get("validation_notes", [])
                notes.extend({"step": step, **i} for i in inform_issues)
                config["validation_notes"] = notes

            # Ask-level issues: pause for user decision
            if ask_issues:
                config["current_step"] = step
                config["status"] = "needs_validation"
                config["validation_issues"] = [{"step": step, **i} for i in ask_issues]
                save_run_config(project_root, config)
                return config

        # Clear prior validation state on success/force
        config.pop("validation_issues", None)

        completed = config.get("completed_steps", [])
        if step not in completed:
            completed.append(step)
        config["completed_steps"] = completed

        # Trigger incremental compliance update (non-blocking on failure)
        compliance_result = run_compliance_update(project_root, step)

        # Split-loop: after build, check if more splits remain
        # Test/changelog/deploy run ONCE after all splits are built
        if step == "build":
            progress = get_build_progress(project_root)
            if progress.get("total_splits", 0) > 0 and not progress.get("all_done", True):
                # More splits remain — loop back to plan for next split
                split_steps = {"plan", "build"}
                config["completed_steps"] = [s for s in completed if s not in split_steps]
                config["current_step"] = "plan"
                config["status"] = "in_progress"
                if compliance_result:
                    config["last_compliance_update"] = {
                        "phase": step,
                        "reports": compliance_result.get("updated_reports", []),
                    }
                # Reset tool counter (between-skill cleanup)
                _reset_tool_counter(project_root)
                save_run_config(project_root, config)
                return config

        # Set next step
        pipeline = config.get("pipeline", PIPELINE_STEPS)
        remaining = [s for s in pipeline if s not in completed]
        config["current_step"] = remaining[0] if remaining else None
        if not remaining:
            config["status"] = "complete"

        if compliance_result:
            config["last_compliance_update"] = {
                "phase": step,
                "reports": compliance_result.get("updated_reports", []),
            }

    elif status == "in_progress":
        config["current_step"] = step

    elif status == "failed":
        config["current_step"] = step
        config["status"] = "failed"

    save_run_config(project_root, config)
    return config


def get_build_progress(project_root: Path) -> dict[str, Any]:
    """Return section-level progress for the build phase.

    Reads shipwright_build_config.json and returns counts plus the next
    section to work on.  Used by the orchestrator autopilot loop and the
    resume-detection logic in SKILL.md.

    Returns split-aware progress:
        split_done: all sections in current split are complete
        all_done: entire build is done (all splits complete)
    """
    from lib.config import collect_all_build_sections

    build_info = collect_all_build_sections(project_root)

    # Current split sections (what the agent works on)
    sections = build_info["current"]
    completed = [s for s in sections if s.get("status") == "complete"]
    in_progress = [s for s in sections if s.get("status") == "in_progress"]
    pending = [s for s in sections if s.get("status") not in ("complete", "in_progress", "failed")]

    # Next section: first in_progress (resume), else first pending
    next_section = None
    if in_progress:
        next_section = in_progress[0]
    elif pending:
        next_section = pending[0]

    # Split awareness
    split_done = len(sections) > 0 and len(completed) == len(sections)
    completed_splits = build_info["completed_splits"]
    total_splits = build_info["total_splits"]

    # all_done: split_done AND no more splits remain
    # For single-split projects (total_splits <= 1), split_done == all_done
    if total_splits > 0:
        all_done = split_done and (len(completed_splits) + 1 >= total_splits)
    else:
        all_done = split_done

    # Total across all splits (for dashboard reporting)
    all_sections = build_info["all"]
    total_all = len(all_sections)
    completed_all = sum(1 for s in all_sections if s.get("status") == "complete")

    return {
        "total": len(sections),
        "completed": len(completed),
        "in_progress": len(in_progress),
        "completed_sections": [s.get("name") for s in completed],
        "next_section": next_section.get("name") if next_section else None,
        "split_done": split_done,
        "all_done": all_done,
        "current_split": build_info["current_split"],
        "completed_splits": completed_splits,
        "total_splits": total_splits,
        "total_all": total_all,
        "completed_all": completed_all,
    }


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
    all_steps = PIPELINE_STEPS + list(CONDITIONAL_STEPS.keys())
    p.add_argument("--step", required=True, choices=all_steps)
    p.add_argument("--status", required=True, choices=["in_progress", "complete", "failed"])
    p.add_argument("--force", action="store_true", help="Skip validation (user override)")

    p = subparsers.add_parser("get-build-progress")
    p.add_argument("--project-root", default=".")

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
        config = update_step(project_root, args.step, args.status, force=args.force)
        print(json.dumps(config, indent=2))

    elif args.command == "get-build-progress":
        result = get_build_progress(project_root)
        print(json.dumps(result, indent=2))

    return 0


if __name__ == "__main__":
    sys.exit(main())
