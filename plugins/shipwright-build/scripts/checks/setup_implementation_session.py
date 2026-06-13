#!/usr/bin/env python3
"""Setup /shipwright-build implementation session.

Usage:
    uv run setup_implementation_session.py --file <section.md> --plugin-root <path> [--session-id <id>]

Output (JSON):
    {
        "success": true/false,
        "mode": "new" | "resume",
        "section_name": "01-auth",
        "section_file": "/path/to/sections/01-auth.md",
        "project_root": "/path/to/project",
        "plugin_root": "/path/to/plugin",
        "branch_name": "build/01-auth-a1b2c3d4",
        "config": { ... },
        "session_id": "<id>"
    }
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from lib.config import load_build_config
from lib.sections import extract_section_name


def detect_project_root(section_path: Path) -> Path:
    """Walk up from section file to find project root (has CLAUDE.md or .git)."""
    current = section_path.parent
    for _ in range(10):  # Max 10 levels up
        if (current / ".git").exists() or (current / "CLAUDE.md").exists():
            return current
        if current.parent == current:
            break
        current = current.parent
    return section_path.parent.parent  # fallback: 2 levels up from section file


def check_branch_exists(branch_name: str) -> bool:
    """Check if git branch exists."""
    try:
        result = subprocess.run(
            ["git", "branch", "--list", branch_name],
            capture_output=True, text=True, encoding="utf-8",
        )
        return branch_name in result.stdout
    except (FileNotFoundError, OSError):
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Setup /shipwright-build session")
    parser.add_argument("--file", required=True, help="Path to section .md file")
    parser.add_argument("--plugin-root", required=True, help="Path to plugin root")
    parser.add_argument("--session-id", help="Session ID from hook context")
    args = parser.parse_args()

    section_path = Path(args.file).resolve()

    if not section_path.exists():
        print(json.dumps({"success": False, "error": f"File not found: {section_path}"}, indent=2))
        return 1

    if not section_path.is_file() or section_path.suffix != ".md":
        print(json.dumps({"success": False, "error": f"Expected markdown file: {section_path}"}, indent=2))
        return 1

    section_name = extract_section_name(section_path)
    if not section_name:
        print(json.dumps({
            "success": False,
            "error": f"Cannot extract section name from: {section_path.name}. Expected NN-kebab-case.md",
        }, indent=2))
        return 1

    project_root = detect_project_root(section_path)
    config = load_build_config(project_root)

    # Derive branch name from session-id + project-slug (not section name)
    # Pattern: build/{slug}-{session-id} or build/{session-id} or build/{section-name}
    slug = ""
    run_config_path = project_root / "shipwright_run_config.json"
    if run_config_path.exists():
        try:
            run_config = json.loads(run_config_path.read_text(encoding="utf-8"))
            project_name = run_config.get("project_summary", {}).get("name", "")
            if project_name:
                slug = re.sub(r"[^a-z0-9]+", "-", project_name.lower()).strip("-")[:20].rstrip("-")
        except (json.JSONDecodeError, OSError):
            pass

    session_short = ""
    if args.session_id:
        session_short = args.session_id.replace("build-", "")

    if slug and session_short:
        branch_name = f"build/{slug}-{session_short}"
    elif session_short:
        branch_name = f"build/{session_short}"
    else:
        branch_name = f"build/{section_name}"
    branch_exists = check_branch_exists(branch_name)

    result = {
        "success": True,
        "mode": "resume" if branch_exists else "new",
        "section_name": section_name,
        "section_file": str(section_path),
        "project_root": str(project_root),
        "plugin_root": args.plugin_root,
        "branch_name": branch_name,
        "branch_exists": branch_exists,
        "config": config,
        "session_id": args.session_id or "",
        "message": f"{'Resuming' if branch_exists else 'Starting'} build for section: {section_name}",
    }

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
