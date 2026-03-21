#!/usr/bin/env python3
"""Setup and manage /shipwright-project session state.

Adapted from deep-project. Simplified: no Claude Code task system integration
(tasks are managed by SKILL.md flow directly).

Usage:
    uv run setup-session.py --file <path_to_spec.md> --plugin-root <path> [--session-id <id>]

Output (JSON):
    {
        "success": true/false,
        "mode": "new" | "resume",
        "planning_dir": "/path/to/planning",
        "initial_file": "/path/to/spec.md",
        "plugin_root": "/path/to/plugin",
        "resume_from_step": <step_number>,
        "state": { ... },
        "split_directories": ["/path/to/planning/01-name", ...],
        "splits_needing_specs": ["02-name", ...],
        "warnings": [],
        "session_id": "<id>"
    }
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from lib.config import (
    check_input_file_changed,
    create_initial_session_state,
    load_session_state,
    save_session_state,
    session_state_exists,
)
from lib.state import detect_state


def validate_input_file(file_path: str) -> tuple[bool, str]:
    """Validate that input file exists, is readable, has content."""
    path = Path(file_path)

    if not path.exists():
        return False, f"File not found: {file_path}"
    if not path.is_file():
        return False, f"Expected a file, got directory: {file_path}"
    if path.suffix != ".md":
        return False, f"Expected markdown file (.md), got: {path.suffix}"

    try:
        content = path.read_text(encoding="utf-8")
        if not content.strip():
            return False, f"File is empty: {file_path}"
    except PermissionError:
        return False, f"Cannot read file (permission denied): {file_path}"

    return True, ""


def main() -> int:
    parser = argparse.ArgumentParser(description="Setup /shipwright-project session")
    parser.add_argument("--file", required=True, help="Path to requirements .md file")
    parser.add_argument("--plugin-root", required=True, help="Path to plugin root")
    parser.add_argument("--session-id", help="Session ID from hook context")
    args = parser.parse_args()

    # Validate input file
    valid, error = validate_input_file(args.file)
    if not valid:
        print(json.dumps({"success": False, "error": error}, indent=2))
        return 1

    # Determine planning directory
    input_path = Path(args.file).resolve()
    planning_dir = input_path.parent

    # Check if session state already exists
    is_new_session = not session_state_exists(planning_dir)

    if is_new_session:
        initial_state = create_initial_session_state(str(input_path))
        save_session_state(planning_dir, initial_state)

    # Check if input file changed
    warnings: list[str] = []
    file_changed = check_input_file_changed(planning_dir, input_path)
    if file_changed:
        warnings.append(f"Input file has changed since session started: {input_path}")

    # Detect current state
    state = detect_state(planning_dir)

    if is_new_session:
        mode = "new"
        resume_from_step = 1
    else:
        mode = "resume"
        resume_from_step = state["resume_step"]

    # Compute split info
    splits = state.get("splits", [])
    splits_with_specs = state.get("splits_with_specs", [])
    split_directories = [str(planning_dir / s) for s in splits]
    splits_needing_specs = [s for s in splits if s not in splits_with_specs]

    result = {
        "success": True,
        "mode": mode,
        "planning_dir": str(planning_dir),
        "initial_file": str(input_path),
        "plugin_root": args.plugin_root,
        "resume_from_step": resume_from_step,
        "state": state,
        "split_directories": split_directories,
        "splits_needing_specs": splits_needing_specs,
        "warnings": warnings,
        "session_id": args.session_id or "",
        "message": f"{'Starting new' if mode == 'new' else 'Resuming'} session in: {planning_dir}",
    }

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
