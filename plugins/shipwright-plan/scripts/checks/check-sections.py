#!/usr/bin/env python3
"""Validate section files against SECTION_MANIFEST.

Usage:
    uv run check-sections.py --planning-dir <path>

Output (JSON):
    {
        "success": true/false,
        "declared": ["01-auth", "02-api"],
        "written": ["01-auth"],
        "missing": ["02-api"],
        "extra": []
    }
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from lib.sections import parse_section_manifest, get_section_files, get_missing_sections


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate section files")
    parser.add_argument("--planning-dir", required=True, help="Path to planning directory")
    args = parser.parse_args()

    planning_dir = Path(args.planning_dir).resolve()
    plan_path = planning_dir / "plan.md"

    result = parse_section_manifest(plan_path)
    if not result.is_valid:
        print(json.dumps({
            "success": False,
            "error": "Cannot parse SECTION_MANIFEST",
            "errors": result.errors,
        }, indent=2))
        return 1

    written = get_section_files(planning_dir)
    missing = get_missing_sections(planning_dir, result.sections)
    extra = [s for s in written if s not in result.sections]

    all_written = len(missing) == 0

    print(json.dumps({
        "success": all_written,
        "declared": result.sections,
        "written": written,
        "missing": missing,
        "extra": extra,
        "message": f"{len(written)}/{len(result.sections)} sections written"
            + (f", {len(missing)} missing" if missing else "")
            + (f", {len(extra)} extra" if extra else ""),
    }, indent=2))
    return 0 if all_written else 1


if __name__ == "__main__":
    sys.exit(main())
