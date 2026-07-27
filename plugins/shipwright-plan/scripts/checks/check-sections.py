#!/usr/bin/env python3
"""Validate section files against SECTION_MANIFEST.

Checks two things:

1. every section declared in the manifest has a file on disk (and reports any
   file the manifest does not declare);
2. the numbering agrees with the dependencies each section declares — a
   prerequisite placed after the section that needs it fails here. A manifest
   that declares no dependencies has nothing to contradict and passes.

Usage:
    uv run check-sections.py --planning-dir <path>

Output (JSON):
    {
        "success": true/false,
        "declared": ["01-auth", "02-api"],
        "written": ["01-auth"],
        "missing": ["02-api"],
        "extra": [],
        "dependencies": {"01-auth": [], "02-api": ["01-auth"]},
        "order_errors": []
    }
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from lib.sections import (
    get_missing_sections,
    get_section_files,
    parse_section_manifest,
    validate_dependency_order,
)


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
    order_errors = validate_dependency_order(result.entries)

    success = not missing and not order_errors

    print(json.dumps({
        "success": success,
        "declared": result.sections,
        "written": written,
        "missing": missing,
        "extra": extra,
        "dependencies": result.dependencies,
        "order_errors": order_errors,
        "message": f"{len(written)}/{len(result.sections)} sections written"
            + (f", {len(missing)} missing" if missing else "")
            + (f", {len(extra)} extra" if extra else "")
            + (f", {len(order_errors)} dependency-order error(s)" if order_errors else ""),
    }, indent=2))
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
