#!/usr/bin/env python3
"""Generate batch task prompts for parallel section writing.

Usage:
    uv run generate-batch-tasks.py --planning-dir <path>

Output (JSON):
    {
        "success": true/false,
        "tasks": [
            {"section": "01-auth", "prompt": "..."},
            {"section": "02-api", "prompt": "..."}
        ]
    }
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from lib.sections import parse_section_manifest, get_missing_sections


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate batch section tasks")
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

    missing = get_missing_sections(planning_dir, result.sections)
    if not missing:
        print(json.dumps({
            "success": True,
            "tasks": [],
            "message": "All sections already written",
        }, indent=2))
        return 0

    # Check if designs/screens/ exists (from /shipwright-design phase)
    project_root = planning_dir.parent
    designs_dir = project_root / "designs" / "screens"
    has_mockups = designs_dir.is_dir()
    mockup_files = sorted(f.name for f in designs_dir.glob("*.html")) if has_mockups else []
    mockup_hint = ""
    if mockup_files:
        mockup_hint = (
            f"\n\nDesign mockups exist at designs/screens/: {', '.join(mockup_files)}.\n"
            "If this section involves UI (pages, layouts, components), add a "
            "`## Design Reference` block before `## Implementation Steps` listing "
            "the relevant mockup(s). Match by name/content. Skip for non-UI sections."
        )

    tasks = []
    for section_name in missing:
        prompt = (
            f"Write section '{section_name}' for the implementation plan.\n\n"
            f"Read the plan at: {plan_path}\n"
            f"Write the section to: {planning_dir}/sections/{section_name}.md\n\n"
            f"The section should be self-contained for /shipwright-build."
            f"{mockup_hint}"
        )
        tasks.append({"section": section_name, "prompt": prompt})

    print(json.dumps({
        "success": True,
        "tasks": tasks,
        "message": f"Generated {len(tasks)} section writing tasks",
    }, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
