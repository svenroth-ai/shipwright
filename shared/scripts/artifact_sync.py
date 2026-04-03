#!/usr/bin/env python3
"""Artifact sync check — read-only drift detection.

Compares current code state against spec FRs using shipwright_sync_config.json mappings.
Output: JSON report of detected drift.
"""

import json
import subprocess
import sys
from pathlib import Path


def detect_drift(project_root: str, ref: str = "HEAD~1..HEAD") -> dict:
    """Detect artifact drift by comparing git diff against sync config."""
    root = Path(project_root)

    # Load sync config
    config_path = root / "shipwright_sync_config.json"
    if not config_path.exists():
        return {
            "drift_detected": False,
            "message": "No shipwright_sync_config.json found — cannot check drift",
            "affected": [],
        }

    config = json.loads(config_path.read_text())
    mappings = config.get("mappings", [])

    # Get changed files from git
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", ref],
            capture_output=True, text=True, cwd=str(root),
        )
        changed_files = [f.strip() for f in result.stdout.strip().split("\n") if f.strip()]
    except (subprocess.SubprocessError, FileNotFoundError):
        return {
            "drift_detected": False,
            "message": "Could not read git diff",
            "affected": [],
        }

    if not changed_files:
        return {"drift_detected": False, "message": "No changes detected", "affected": []}

    # Match changed files against mappings
    import fnmatch
    affected = []

    for mapping in mappings:
        pattern = mapping.get("pattern", "")
        matching_files = [f for f in changed_files if fnmatch.fnmatch(f, pattern)]
        if matching_files:
            affected.append({
                "pattern": pattern,
                "changed_files": matching_files,
                "artifacts": mapping.get("artifacts", []),
                "frs": mapping.get("frs", []),
                "category": mapping.get("category", "unknown"),
            })

    return {
        "drift_detected": len(affected) > 0,
        "message": f"{len(affected)} mapping(s) affected" if affected else "No drift detected",
        "affected": affected,
        "changed_files_total": len(changed_files),
    }


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Artifact sync drift detection")
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--mode", choices=["detect"], default="detect")
    parser.add_argument("--ref", default="HEAD~1..HEAD", help="Git ref range")
    args = parser.parse_args()

    result = detect_drift(args.project_root, args.ref)
    print(json.dumps(result, indent=2))
    sys.exit(0 if not result["drift_detected"] else 1)


if __name__ == "__main__":
    main()
