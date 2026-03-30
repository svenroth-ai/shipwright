#!/usr/bin/env python3
"""Mark a section as complete with commit hash.

Usage:
    uv run update_section_state.py --section <name> --status <status> --commit <hash>

Updates shipwright_build_config.json in the project root.
"""

import argparse
import json
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Update section state")
    parser.add_argument("--section", required=True, help="Section name (e.g., 01-auth)")
    parser.add_argument("--status", required=True, choices=["in_progress", "complete", "failed"])
    parser.add_argument("--commit", help="Git commit hash")
    parser.add_argument("--tests-passed", type=int, help="Number of tests passed")
    parser.add_argument("--tests-total", type=int, help="Total number of tests")
    parser.add_argument("--review-findings", help="JSON array of code review findings")
    parser.add_argument("--project-root", help="Project root (default: cwd)")
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve() if args.project_root else Path.cwd()
    config_path = project_root / "shipwright_build_config.json"

    config = {}
    if config_path.exists():
        try:
            config = json.loads(config_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass

    sections = config.get("sections", [])

    # Update or add section
    found = False
    # Parse review findings if provided
    review_findings = None
    if args.review_findings:
        try:
            review_findings = json.loads(args.review_findings)
        except json.JSONDecodeError:
            print(json.dumps({"success": False, "error": "Invalid JSON for --review-findings"}))
            return 1

    for section in sections:
        if section.get("name") == args.section:
            section["status"] = args.status
            if args.commit:
                section["commit"] = args.commit
            if args.tests_passed is not None:
                section["tests_passed"] = args.tests_passed
            if args.tests_total is not None:
                section["tests_total"] = args.tests_total
            if review_findings is not None:
                section["code_review_findings"] = review_findings
            found = True
            break

    if not found:
        entry = {"name": args.section, "status": args.status}
        if args.commit:
            entry["commit"] = args.commit
        if args.tests_passed is not None:
            entry["tests_passed"] = args.tests_passed
        if args.tests_total is not None:
            entry["tests_total"] = args.tests_total
        if review_findings is not None:
            entry["code_review_findings"] = review_findings
        sections.append(entry)

    config["sections"] = sections
    config_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")

    print(json.dumps({"success": True, "section": args.section, "status": args.status}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
