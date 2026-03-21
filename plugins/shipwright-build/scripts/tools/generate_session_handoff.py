#!/usr/bin/env python3
"""Generate session handoff document.

Usage:
    uv run generate_session_handoff.py --project-root <path> --section <name> --status <status>

Writes agent_docs/session_handoff.md with current session state.
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def get_git_status() -> str:
    """Get brief git status."""
    try:
        result = subprocess.run(
            ["git", "status", "--short"],
            capture_output=True, text=True, encoding="utf-8",
        )
        return result.stdout.strip() or "(clean)"
    except (FileNotFoundError, OSError):
        return "(git not available)"


def get_recent_commits(n: int = 5) -> str:
    """Get recent commit log."""
    try:
        result = subprocess.run(
            ["git", "log", "--oneline", f"-{n}"],
            capture_output=True, text=True, encoding="utf-8",
        )
        return result.stdout.strip()
    except (FileNotFoundError, OSError):
        return "(git not available)"


def get_current_branch() -> str:
    """Get current git branch."""
    try:
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            capture_output=True, text=True, encoding="utf-8",
        )
        return result.stdout.strip()
    except (FileNotFoundError, OSError):
        return "(unknown)"


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate session handoff")
    parser.add_argument("--project-root", required=True, help="Project root")
    parser.add_argument("--section", required=True, help="Current section name")
    parser.add_argument("--status", required=True, choices=["in_progress", "complete"])
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()
    handoff_path = project_root / "agent_docs" / "session_handoff.md"
    handoff_path.parent.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    branch = get_current_branch()
    git_status = get_git_status()
    recent_commits = get_recent_commits()

    content = f"""# Session Handoff

Generated: {timestamp}

## Current State

- **Section**: {args.section}
- **Status**: {args.status}
- **Branch**: {branch}

## Git Status

```
{git_status}
```

## Recent Commits

```
{recent_commits}
```

## How to Resume

1. Check out the branch: `git checkout {branch}`
2. Run `/shipwright-build @sections/{args.section}.md`
3. The skill will detect existing state and resume automatically

## Notes

(Add any context that would help the next session)
"""

    handoff_path.write_text(content, encoding="utf-8")

    print(json.dumps({
        "success": True,
        "path": str(handoff_path),
        "section": args.section,
        "status": args.status,
    }, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
