#!/usr/bin/env python3
"""SessionStart hook: Detect CLAUDE.md drift from source code changes.

Compares modification timestamps of key project files against CLAUDE.md.
If source files changed more recently than CLAUDE.md, warns the agent
that documentation may be outdated.

Exit codes:
  0 = allow (always — informational warning only, never blocks)

Rationale: When code architecture changes but CLAUDE.md is not updated,
agents work with stale context. This leads to incorrect assumptions
about project structure, available commands, and conventions.

Checked files:
  - CLAUDE.md vs. package.json, pyproject.toml, tsconfig.json
  - CLAUDE.md vs. src/ directory (newest file)
  - CLAUDE.md vs. key config files
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


# Files that indicate structural changes when modified
KEY_FILES = [
    "package.json",
    "pyproject.toml",
    "tsconfig.json",
    "Cargo.toml",
    "go.mod",
    "requirements.txt",
    "docker-compose.yml",
    "Dockerfile",
]

# Directories where changes likely affect CLAUDE.md accuracy
KEY_DIRS = [
    "src",
    "app",
    "lib",
    "packages",
]


def get_mtime(path: str) -> float | None:
    """Get file modification time, or None if not found."""
    try:
        return os.path.getmtime(path)
    except OSError:
        return None


def get_newest_in_dir(directory: str, max_depth: int = 2) -> float | None:
    """Get the newest modification time in a directory (limited depth)."""
    newest = None
    try:
        for root, dirs, files in os.walk(directory):
            # Limit depth
            depth = root.replace(directory, "").count(os.sep)
            if depth >= max_depth:
                dirs.clear()
                continue
            # Skip hidden dirs, node_modules, __pycache__
            dirs[:] = [
                d for d in dirs
                if not d.startswith(".") and d not in ("node_modules", "__pycache__", "vendor", "dist", "build")
            ]
            for f in files:
                if f.startswith("."):
                    continue
                fp = os.path.join(root, f)
                mt = get_mtime(fp)
                if mt and (newest is None or mt > newest):
                    newest = mt
    except OSError:
        pass
    return newest


def check_drift(project_root: str) -> list[str]:
    """Check if key files are newer than CLAUDE.md.

    Returns list of files that changed after CLAUDE.md.
    """
    claude_md = os.path.join(project_root, "CLAUDE.md")
    claude_mtime = get_mtime(claude_md)

    if claude_mtime is None:
        return []  # No CLAUDE.md = nothing to drift from

    drifted = []

    # Check key files
    for fname in KEY_FILES:
        fpath = os.path.join(project_root, fname)
        mt = get_mtime(fpath)
        if mt and mt > claude_mtime:
            drifted.append(fname)

    # Check key directories
    for dirname in KEY_DIRS:
        dpath = os.path.join(project_root, dirname)
        if os.path.isdir(dpath):
            mt = get_newest_in_dir(dpath)
            if mt and mt > claude_mtime:
                drifted.append(f"{dirname}/ (source changes)")

    return drifted


def main() -> int:
    # SessionStart hook — no stdin payload needed
    # We just check the current working directory
    project_root = os.getcwd()

    drifted = check_drift(project_root)

    if drifted:
        drift_list = ", ".join(drifted)
        warning = {
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": (
                    f"DRIFT WARNING: CLAUDE.md may be outdated. "
                    f"The following files changed since CLAUDE.md was last modified: {drift_list}. "
                    f"Consider updating CLAUDE.md to reflect current project state before "
                    f"making architectural decisions."
                ),
            }
        }
        print(json.dumps(warning))

    return 0  # Never block — informational only


if __name__ == "__main__":
    sys.exit(main())
