#!/usr/bin/env python3
"""Mark a section as complete with commit hash.

Usage:
    uv run update_section_state.py --section <name> --status <status> --commit <hash>
    uv run update_section_state.py --section <name> --status complete --commit <hash> \
        --visual-fidelity partial --visual-groups-file /tmp/groups.json \
        --visual-screen 01-login.html --visual-screen 02-register.html

Updates shipwright_build_config.json in the project root.
Also updates visual-build-report.json (canonical Build→Test visual artifact).
"""

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path


def _atomic_write_json(path: Path, data: dict) -> None:
    """Write JSON atomically via temp file + rename."""
    content = json.dumps(data, indent=2) + "\n"
    fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        os.write(fd, content.encode("utf-8"))
        os.close(fd)
        os.replace(tmp_path, str(path))
    except BaseException:
        os.close(fd) if not os.get_inheritable(fd) else None
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _update_visual_build_report(
    project_root: Path,
    section: str,
    visual_fidelity: str,
    visual_groups: list[dict] | None,
    visual_screens: list[str],
    build_complete: bool = False,
) -> None:
    """Update visual-build-report.json with screen-centric visual data for this section.

    Read-merge-write: preserves data from other sections. Validates screen uniqueness
    (warns on duplicates, last-writer-wins).
    """
    report_path = project_root / "visual-build-report.json"

    report: dict = {"build_complete": False, "screens": {}}
    if report_path.exists():
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            report = {"build_complete": False, "screens": {}}

    if "screens" not in report:
        report["screens"] = {}

    # Derive per-screen status from groups
    groups_fixed = []
    groups_parked = []
    diagnosis = ""
    if visual_groups:
        for g in visual_groups:
            status = g.get("status", "n/a")
            if status == "fixed":
                groups_fixed.append(g.get("group", ""))
            elif status == "parked":
                groups_parked.append(g.get("group", ""))
                if g.get("diagnosis"):
                    diagnosis = g["diagnosis"]

    # Determine per-screen status: worst-case if screen appears in any parked group
    screen_in_parked = set()
    if visual_groups:
        for g in visual_groups:
            if g.get("status") == "parked":
                for s in g.get("screens", []):
                    screen_in_parked.add(s)

    for screen in visual_screens:
        # Warn on duplicate (screen already owned by different section)
        existing = report["screens"].get(screen)
        if existing and existing.get("section") != section:
            print(
                f"WARNING: Screen {screen} already owned by section "
                f"{existing['section']}, overwriting with {section}",
                file=sys.stderr,
            )

        screen_status = "partial" if screen in screen_in_parked else visual_fidelity
        report["screens"][screen] = {
            "section": section,
            "status": screen_status,
            "groups_fixed": groups_fixed,
            "groups_parked": groups_parked,
            "diagnosis": diagnosis,
        }

    if build_complete:
        report["build_complete"] = True

    _atomic_write_json(report_path, report)


def main() -> int:
    parser = argparse.ArgumentParser(description="Update section state")
    parser.add_argument("--section", required=True, help="Section name (e.g., 01-auth)")
    parser.add_argument("--status", required=True, choices=["in_progress", "complete", "failed"])
    parser.add_argument("--commit", help="Git commit hash")
    parser.add_argument("--tests-passed", type=int, help="Number of tests passed")
    parser.add_argument("--tests-total", type=int, help="Total number of tests")
    parser.add_argument("--review-findings", help="JSON array of code review findings")
    parser.add_argument("--review-type", choices=["self-review", "full-review"],
                        help="Type of code review performed")
    parser.add_argument("--project-root", help="Project root (default: cwd)")
    # Visual comparison fields
    parser.add_argument("--visual-fidelity", choices=["full", "partial", "skipped"],
                        help="Visual fidelity result for this section")
    parser.add_argument("--visual-groups-file",
                        help="Path to temp JSON file with visual groups array (cleaned up after read)")
    parser.add_argument("--visual-screen", action="append", dest="visual_screens", metavar="FILENAME",
                        help="Screen filename checked in this section (repeatable)")
    parser.add_argument("--build-complete", action="store_true",
                        help="Mark build as complete in visual-build-report.json")
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

    # Parse review findings if provided
    review_findings = None
    if args.review_findings:
        try:
            review_findings = json.loads(args.review_findings)
        except json.JSONDecodeError:
            print(json.dumps({"success": False, "error": "Invalid JSON for --review-findings"}))
            return 1

    # Parse visual groups from file if provided
    visual_groups = None
    if args.visual_groups_file:
        groups_path = Path(args.visual_groups_file)
        try:
            visual_groups = json.loads(groups_path.read_text(encoding="utf-8"))
            # Clean up temp file after reading
            groups_path.unlink(missing_ok=True)
        except (json.JSONDecodeError, OSError) as e:
            print(json.dumps({"success": False, "error": f"Failed to read visual groups file: {e}"}))
            return 1

    # Build section data update
    def _apply_to_section(section_data: dict) -> None:
        section_data["status"] = args.status
        if args.commit:
            section_data["commit"] = args.commit
        if args.tests_passed is not None:
            section_data["tests_passed"] = args.tests_passed
        if args.tests_total is not None:
            section_data["tests_total"] = args.tests_total
        if review_findings is not None:
            section_data["code_review_findings"] = review_findings
        if args.review_type:
            section_data["review_type"] = args.review_type
        if args.visual_fidelity:
            section_data["visual_fidelity"] = args.visual_fidelity
            section_data["visual_report"] = "visual-build-report.json"

    # Update or add section
    found = False
    for section in sections:
        if section.get("name") == args.section:
            _apply_to_section(section)
            found = True
            break

    if not found:
        entry = {"name": args.section}
        _apply_to_section(entry)
        sections.append(entry)

    config["sections"] = sections
    _atomic_write_json(config_path, config)

    # Update visual-build-report.json if visual data provided
    if args.visual_fidelity and args.visual_screens:
        _update_visual_build_report(
            project_root,
            section=args.section,
            visual_fidelity=args.visual_fidelity,
            visual_groups=visual_groups,
            visual_screens=args.visual_screens,
            build_complete=args.build_complete,
        )

    print(json.dumps({"success": True, "section": args.section, "status": args.status}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
