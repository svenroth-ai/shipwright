#!/usr/bin/env python3
"""Setup and manage /shipwright-plan session state.

Usage:
    uv run setup-planning-session.py --file <spec.md> --plugin-root <path> [--session-id <id>]

Output (JSON):
    {
        "success": true/false,
        "mode": "new" | "resume",
        "planning_dir": "/path/to/planning",
        "spec_file": "/path/to/spec.md",
        "plugin_root": "/path/to/plugin",
        "resume_from_step": <step_number>,
        "state": { ... },
        "session_id": "<id>"
    }
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from lib.config import load_global_config, is_external_review_enabled, is_e2e_enabled
from lib.sections import parse_section_manifest, get_missing_sections


SESSION_STATE_FILE = "shipwright_plan_session.json"
INTERVIEW_FILE = "shipwright_plan_interview.md"
PLAN_FILE = "plan.md"
E2E_PLAN_FILE = "claude-plan-e2e.md"


def detect_state(planning_dir: Path) -> dict:
    """Detect planning session state from file existence."""
    interview_exists = (planning_dir / INTERVIEW_FILE).exists()
    plan_exists = (planning_dir / PLAN_FILE).exists()
    e2e_exists = (planning_dir / E2E_PLAN_FILE).exists()

    # Parse sections from plan if it exists
    sections_declared = []
    sections_written = []
    sections_missing = []

    if plan_exists:
        result = parse_section_manifest(planning_dir / PLAN_FILE)
        if result.is_valid:
            sections_declared = result.sections
            sections_missing = get_missing_sections(planning_dir, sections_declared)
            sections_written = [s for s in sections_declared if s not in sections_missing]

    # Determine resume step
    if plan_exists and sections_declared and not sections_missing:
        resume_step = 8  # E2E or completion
    elif plan_exists and sections_declared and sections_missing:
        resume_step = 6  # Section splitting
    elif plan_exists:
        resume_step = 5  # External review
    elif interview_exists:
        resume_step = 3  # Context check
    else:
        resume_step = 1  # Research

    return {
        "interview_exists": interview_exists,
        "plan_exists": plan_exists,
        "e2e_exists": e2e_exists,
        "sections_declared": sections_declared,
        "sections_written": sections_written,
        "sections_missing": sections_missing,
        "resume_step": resume_step,
    }


def validate_spec_file(file_path: str) -> tuple[bool, str]:
    """Validate spec file."""
    path = Path(file_path)
    if not path.exists():
        return False, f"File not found: {file_path}"
    if not path.is_file():
        return False, f"Expected file, got directory: {file_path}"
    if path.suffix != ".md":
        return False, f"Expected markdown file, got: {path.suffix}"
    try:
        content = path.read_text(encoding="utf-8")
        if not content.strip():
            return False, f"File is empty: {file_path}"
    except PermissionError:
        return False, f"Cannot read file: {file_path}"
    return True, ""


def main() -> int:
    parser = argparse.ArgumentParser(description="Setup /shipwright-plan session")
    parser.add_argument("--file", required=True, help="Path to spec .md file")
    parser.add_argument("--plugin-root", required=True, help="Path to plugin root")
    parser.add_argument("--session-id", help="Session ID from hook context")
    args = parser.parse_args()

    valid, error = validate_spec_file(args.file)
    if not valid:
        print(json.dumps({"success": False, "error": error}, indent=2))
        return 1

    spec_path = Path(args.file).resolve()
    planning_dir = spec_path.parent

    # Ensure sections directory exists
    (planning_dir / "sections").mkdir(exist_ok=True)

    # Check session state
    state_file = planning_dir / SESSION_STATE_FILE
    is_new = not state_file.exists()

    if is_new:
        import hashlib
        from datetime import datetime, timezone

        content_hash = f"sha256:{hashlib.sha256(spec_path.read_bytes()).hexdigest()}"
        state_data = {
            "spec_file_hash": content_hash,
            "session_created_at": datetime.now(timezone.utc).isoformat(),
        }
        state_file.write_text(json.dumps(state_data, indent=2), encoding="utf-8")

    state = detect_state(planning_dir)

    # Load config for capabilities
    global_config = load_global_config(args.plugin_root)

    result = {
        "success": True,
        "mode": "new" if is_new else "resume",
        "planning_dir": str(planning_dir),
        "spec_file": str(spec_path),
        "plugin_root": args.plugin_root,
        "resume_from_step": state["resume_step"] if not is_new else 1,
        "state": state,
        "external_review_enabled": is_external_review_enabled(global_config),
        "e2e_enabled": is_e2e_enabled(global_config),
        "session_id": args.session_id or "",
        "message": f"{'Starting new' if is_new else 'Resuming'} planning session in: {planning_dir}",
    }

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
