#!/usr/bin/env python3
"""Update a section's status in agent_docs/current_sprint.md.

Parses the Markdown table, finds the matching section row, and updates
the Status and Commit columns.

Usage:
    uv run update_sprint.py --project-root <path> --section "01-project-setup" \
        --status complete --commit abc1234
"""

import argparse
import json
import re
import sys
from pathlib import Path


def update_sprint_table(content: str, section: str, status: str, commit: str) -> str:
    """Update a section row in the sprint Markdown table.

    Expects table rows like:
        | 01 | project-setup | not_started | — |
    Section matching is flexible: matches on the section name part
    (e.g. "01-project-setup" matches "project-setup" in the table).
    """
    # Extract the name part (without numeric prefix)
    section_name = re.sub(r"^\d+-", "", section)

    lines = content.splitlines()
    updated = False

    for i, line in enumerate(lines):
        # Match table rows (| num | name | status | commit |)
        if "|" in line and section_name in line:
            # Split by |, update status and commit columns
            parts = [p.strip() for p in line.split("|")]
            # parts: ['', num, name, status, commit, '']
            if len(parts) >= 6:
                parts[3] = status
                parts[4] = commit or "—"
                lines[i] = "| " + " | ".join(parts[1:-1]) + " |"
                updated = True
                break

    if not updated:
        return content

    return "\n".join(lines) + "\n" if content.endswith("\n") else "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Update section in current_sprint.md")
    parser.add_argument("--project-root", required=True, help="Project root directory")
    parser.add_argument("--section", required=True, help="Section name (e.g., 01-project-setup)")
    parser.add_argument("--status", required=True, help="New status (e.g., complete, in_progress)")
    parser.add_argument("--commit", default="", help="Commit hash")
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()
    sprint_path = project_root / "agent_docs" / "current_sprint.md"

    if not sprint_path.exists():
        print(json.dumps({"success": False, "reason": "current_sprint.md not found"}))
        return 0

    content = sprint_path.read_text(encoding="utf-8")
    updated = update_sprint_table(content, args.section, args.status, args.commit)

    if updated == content:
        print(json.dumps({"success": False, "reason": f"Section '{args.section}' not found in table"}))
        return 0

    sprint_path.write_text(updated, encoding="utf-8")
    print(json.dumps({"success": True, "section": args.section, "status": args.status}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
