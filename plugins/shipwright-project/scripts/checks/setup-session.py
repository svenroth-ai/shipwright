#!/usr/bin/env python3
"""Setup and manage /shipwright-project session state.

Supports three input modes:
  - file:   uv run setup-session.py --file <path.md> --plugin-root <path>
  - inline: uv run setup-session.py --planning-dir <path> --plugin-root <path> --input-mode inline
  - chat:   uv run setup-session.py --planning-dir <path> --plugin-root <path> --input-mode chat

Output (JSON):
    {
        "success": true/false,
        "mode": "new" | "resume",
        "input_mode": "file" | "inline" | "chat",
        "planning_dir": "/path/to/planning",
        "initial_file": "/path/to/spec.md" | null,
        "plugin_root": "/path/to/plugin",
        "resume_from_step": <step_number>,
        "state": { ... },
        "session_id": "<id>"
    }
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from lib.config import (
    check_input_file_changed,
    create_initial_session_state,
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
    parser.add_argument("--file", help="Path to requirements .md file (file mode)")
    parser.add_argument("--planning-dir", help="Planning directory (inline/chat mode)")
    parser.add_argument("--plugin-root", required=True, help="Path to plugin root")
    parser.add_argument("--session-id", help="Session ID from hook context")
    parser.add_argument("--input-mode", choices=["file", "inline", "chat"], default="file",
                        help="Input mode: file, inline, or chat")
    parser.add_argument("--force", action="store_true", help="Overwrite existing session")
    args = parser.parse_args()

    # Determine input mode and planning directory
    input_mode = args.input_mode
    initial_file = None

    if args.file:
        # File mode (explicit or inferred)
        input_mode = "file"
        valid, error = validate_input_file(args.file)
        if not valid:
            print(json.dumps({"success": False, "error": error}, indent=2))
            return 1
        input_path = Path(args.file).resolve()
        planning_dir = input_path.parent
        initial_file = str(input_path)
    elif args.planning_dir:
        # Inline or chat mode
        planning_dir = Path(args.planning_dir).resolve()
        planning_dir.mkdir(parents=True, exist_ok=True)
    else:
        print(json.dumps({
            "success": False,
            "error": "Either --file or --planning-dir is required",
        }, indent=2))
        return 1

    # Check if session state already exists
    is_new_session = not session_state_exists(planning_dir)

    if not is_new_session and args.force:
        is_new_session = True

    if is_new_session:
        if initial_file:
            initial_state = create_initial_session_state(initial_file)
        else:
            # No file — create minimal state
            initial_state = {
                "input_mode": input_mode,
                "session_created_at": datetime.now(timezone.utc).isoformat(),
            }
        save_session_state(planning_dir, initial_state)

    # Check if input file changed (only relevant for file mode)
    warnings: list[str] = []
    if initial_file:
        file_changed = check_input_file_changed(planning_dir, initial_file)
        if file_changed:
            warnings.append(f"Input file has changed since session started: {initial_file}")

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
        "input_mode": input_mode,
        "planning_dir": str(planning_dir),
        "initial_file": initial_file,
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
