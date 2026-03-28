#!/usr/bin/env python3
"""Incremental compliance update — called by orchestrator after each phase.

Usage:
    uv run update_compliance.py --project-root <path> --phase <name>

Only regenerates reports affected by the completed phase.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.lib.data_collector import collect_all
from scripts.lib.rtm_generator import generate_file as generate_rtm
from scripts.lib.test_evidence import generate_file as generate_test_evidence
from scripts.lib.change_history import generate_file as generate_change_history
from scripts.lib.compliance_report import generate_file as generate_dashboard
from scripts.lib.sbom_generator import generate_file as generate_sbom

# Phase -> which reports to regenerate
PHASE_REPORTS = {
    "project": ["rtm", "dashboard"],
    "design": ["dashboard"],
    "plan": ["rtm", "dashboard"],
    "compliance": ["dashboard"],
    "build": ["rtm", "test_evidence", "change_history", "dashboard"],
    "test": ["test_evidence", "dashboard"],
    "deploy": ["dashboard"],
    "changelog": ["change_history", "dashboard"],
}

GENERATORS = {
    "rtm": generate_rtm,
    "test_evidence": generate_test_evidence,
    "change_history": generate_change_history,
    "dashboard": generate_dashboard,
    "sbom": generate_sbom,
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Incremental compliance update")
    parser.add_argument("--project-root", required=True, help="Project root directory")
    parser.add_argument("--phase", required=True, help="Completed phase name")
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()
    phase = args.phase

    reports_to_update = PHASE_REPORTS.get(phase, ["dashboard"])

    # Collect data once
    data = collect_all(project_root)

    updated = []
    for report_name in reports_to_update:
        gen_fn = GENERATORS.get(report_name)
        if gen_fn:
            path = gen_fn(project_root, data)
            updated.append(str(path.relative_to(project_root)))

    # Update compliance config
    config_path = project_root / "shipwright_compliance_config.json"
    if config_path.exists():
        config = json.loads(config_path.read_text(encoding="utf-8"))
    else:
        config = {"status": "in_progress", "artifacts": {}}

    phases_covered = config.get("phases_covered", [])
    if phase not in phases_covered:
        phases_covered.append(phase)
    config["phases_covered"] = phases_covered

    config_path.write_text(json.dumps(config, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    output = {
        "success": True,
        "phase": phase,
        "updated_reports": updated,
    }
    print(json.dumps(output, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
