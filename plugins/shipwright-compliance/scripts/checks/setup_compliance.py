#!/usr/bin/env python3
"""Validate project state before generating compliance reports.

Usage:
    uv run setup_compliance.py --project-root <path> --plugin-root <path> --session-id <id>

Output: JSON with available data sources and existing reports.
"""

import argparse
import json
import sys
from pathlib import Path


CONFIG_FILES = {
    "run_config": "shipwright_run_config.json",
    "project_config": "shipwright_project_config.json",
    "plan_config": "shipwright_plan_config.json",
    "build_config": "shipwright_build_config.json",
}

REPORT_FILES = {
    "dashboard": "compliance/dashboard.md",
    "rtm": "compliance/traceability-matrix.md",
    "test_evidence": "compliance/test-evidence.md",
    "change_history": "compliance/change-history.md",
    "sbom": "compliance/sbom.md",
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Setup compliance reporting")
    parser.add_argument("--project-root", required=True, help="Project root directory")
    parser.add_argument("--plugin-root", required=True, help="Plugin root directory")
    parser.add_argument("--session-id", default="", help="Session ID")
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()

    # Check available data
    available_data = {}
    for key, filename in CONFIG_FILES.items():
        available_data[key] = (project_root / filename).exists()

    available_data["decision_log"] = (project_root / "agent_docs" / "decision_log.md").exists()
    available_data["git_history"] = (project_root / ".git").exists()
    available_data["package_json"] = (project_root / "package.json").exists()
    available_data["pyproject_toml"] = (project_root / "pyproject.toml").exists()

    # Check existing reports
    existing_reports = {}
    for key, filepath in REPORT_FILES.items():
        existing_reports[key] = (project_root / filepath).exists()

    # Determine mode
    has_any_report = any(existing_reports.values())
    has_any_data = any(available_data.values())

    # Detect current phase
    phase = "unknown"
    if available_data.get("build_config"):
        phase = "build"
    elif available_data.get("plan_config"):
        phase = "plan"
    elif available_data.get("project_config"):
        phase = "project"

    # Check run config for more accurate phase
    run_config_path = project_root / CONFIG_FILES["run_config"]
    if run_config_path.exists():
        try:
            run_config = json.loads(run_config_path.read_text(encoding="utf-8"))
            phase = run_config.get("current_step", phase)
        except (json.JSONDecodeError, OSError):
            pass

    output = {
        "success": True,
        "phase": phase,
        "available_data": available_data,
        "existing_reports": existing_reports,
        "mode": "update" if has_any_report else "new",
        "has_data": has_any_data,
        "session_id": args.session_id,
        "plugin_root": args.plugin_root,
    }

    print(json.dumps(output, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
