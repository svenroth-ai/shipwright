#!/usr/bin/env python3
"""Archive completed split sections before transitioning to the next split.

Usage:
    uv run archive_split.py --project-root <path> --next-split <name>

Moves current ``sections[]`` to ``split_{prefix}_sections``, updates
``current_split`` and ``completed_splits``, and clears ``sections[]``
so /shipwright-plan can populate it for the next split.

Output (JSON):
    {
        "success": true,
        "archived_key": "split_01_sections",
        "archived_count": 8,
        "current_split": "02-course-platform",
        "completed_splits": ["01-foundation"]
    }
"""

import argparse
import json
import sys
from pathlib import Path

# Allow imports from sibling packages
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lib.config import read_config, write_config


def archive_split(project_root: Path, next_split: str) -> dict:
    """Archive current split sections and transition to next split.

    Args:
        project_root: Path to the target project.
        next_split: Name of the next split (e.g. "02-course-platform").

    Returns:
        Result dict with archive details.
    """
    config = read_config("build", project_root)

    current_split = config.get("current_split", "")
    sections = config.get("sections", [])
    completed_splits = config.get("completed_splits", [])

    if not current_split:
        return {"success": False, "error": "No current_split set in build config"}

    if not sections:
        return {"success": False, "error": "No sections to archive"}

    # Extract prefix: "01-foundation" -> "01"
    prefix = current_split.split("-", 1)[0]
    archive_key = f"split_{prefix}_sections"

    # Idempotent: if already archived, skip
    if archive_key in config:
        return {
            "success": True,
            "archived_key": archive_key,
            "archived_count": len(config[archive_key]),
            "current_split": config.get("current_split", ""),
            "completed_splits": config.get("completed_splits", []),
            "skipped": True,
            "message": f"{archive_key} already exists, skipping archive",
        }

    # Archive: copy sections to split_NN_sections
    config[archive_key] = sections

    # Update completed_splits
    if current_split not in completed_splits:
        completed_splits.append(current_split)
    config["completed_splits"] = completed_splits

    # Transition to next split
    config["current_split"] = next_split
    config["sections"] = []

    write_config("build", project_root, config)

    return {
        "success": True,
        "archived_key": archive_key,
        "archived_count": len(sections),
        "current_split": next_split,
        "completed_splits": completed_splits,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Archive completed split sections")
    parser.add_argument("--project-root", required=True, help="Target project root")
    parser.add_argument("--next-split", required=True, help="Name of the next split")
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()
    result = archive_split(project_root, args.next_split)
    print(json.dumps(result, indent=2))
    return 0 if result.get("success") else 1


if __name__ == "__main__":
    sys.exit(main())
