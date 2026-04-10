#!/usr/bin/env python3
"""Write shipwright_plan_config.json to the project root.

Writes to the project root (not planning_dir) so that shared/scripts/lib/config.py
can find it. Supports both in_progress (early tracking) and complete (final) status.

Usage:
    uv run write-plan-config.py --project-root <path> --status in_progress
    uv run write-plan-config.py --project-root <path> --status complete \
        --split <name> --sections <count>
"""

import argparse
import json
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Write shipwright plan config")
    parser.add_argument("--project-root", required=True, help="Project root directory")
    parser.add_argument("--status", required=True, choices=["in_progress", "complete"],
                        help="Config status")
    parser.add_argument("--split", help="Current split name (for complete status)")
    parser.add_argument("--sections", type=int, help="Number of sections (for complete status)")
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()

    if args.status == "in_progress":
        config = {"status": "in_progress"}
    else:
        config = {
            "status": "complete",
            "split": args.split or "",
            "sections": args.sections or 0,
        }

    config_path = project_root / "shipwright_plan_config.json"
    config_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")

    print(json.dumps(config, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
