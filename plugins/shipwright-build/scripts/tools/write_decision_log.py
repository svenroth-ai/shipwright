#!/usr/bin/env python3
"""Write entries to agent_docs/decision_log.md.

Usage:
    uv run write_decision_log.py --project-root <path> --section <name> --decisions '<json>'

Decisions JSON format:
    [{"decision": "Use X", "reason": "Because Y", "category": "architecture"}]
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Write decision log entries")
    parser.add_argument("--project-root", required=True, help="Project root directory")
    parser.add_argument("--section", required=True, help="Section name")
    parser.add_argument("--decisions", required=True, help="Decisions as JSON array")
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()
    log_path = project_root / "agent_docs" / "decision_log.md"

    try:
        decisions = json.loads(args.decisions)
    except json.JSONDecodeError as e:
        print(json.dumps({"success": False, "error": f"Invalid JSON: {e}"}, indent=2))
        return 1

    if not decisions:
        print(json.dumps({"success": True, "message": "No decisions to log"}, indent=2))
        return 0

    # Ensure agent_docs directory exists
    log_path.parent.mkdir(parents=True, exist_ok=True)

    # Read existing content or create header
    if log_path.exists():
        content = log_path.read_text(encoding="utf-8")
    else:
        content = "# Decision Log\n\nArchitectural and design decisions made during implementation.\n"

    # Append new entries
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    content += f"\n## {args.section} ({timestamp})\n\n"

    for d in decisions:
        decision = d.get("decision", "")
        reason = d.get("reason", "")
        category = d.get("category", "general")
        content += f"- **{decision}** [{category}]\n"
        if reason:
            content += f"  - Reason: {reason}\n"

    log_path.write_text(content, encoding="utf-8")

    print(json.dumps({
        "success": True,
        "entries_written": len(decisions),
        "path": str(log_path),
    }, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
