#!/usr/bin/env python3
"""Generate all compliance reports from scratch.

Usage:
    uv run generate_full_report.py --project-root <path>

Output: JSON summary of generated artifacts.
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add parent dirs to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.lib.data_collector import collect_all
from scripts.lib.rtm_generator import generate_file as generate_rtm
from scripts.lib.test_evidence import generate_file as generate_test_evidence
from scripts.lib.change_history import generate_file as generate_change_history
from scripts.lib.compliance_report import generate_file as generate_dashboard
from scripts.lib.sbom_generator import generate_file as generate_sbom


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate full compliance report")
    parser.add_argument("--project-root", required=True, help="Project root directory")
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()

    # Collect all data once
    data = collect_all(project_root)

    # Generate all reports
    artifacts = {}

    rtm_path = generate_rtm(project_root, data)
    artifacts["rtm"] = str(rtm_path.relative_to(project_root))

    te_path = generate_test_evidence(project_root, data)
    artifacts["test_evidence"] = str(te_path.relative_to(project_root))

    ch_path = generate_change_history(project_root, data)
    artifacts["change_history"] = str(ch_path.relative_to(project_root))

    sbom_path = generate_sbom(project_root, data)
    artifacts["sbom"] = str(sbom_path.relative_to(project_root))

    # Dashboard last — it references other reports
    dashboard_path = generate_dashboard(project_root, data)
    artifacts["dashboard"] = str(dashboard_path.relative_to(project_root))

    # Write compliance config
    config = {
        "status": "complete",
        "last_full_generation": data.timestamp,
        "artifacts": {
            name: {
                "path": path,
                "last_updated": data.timestamp,
            }
            for name, path in artifacts.items()
        },
        "summary": {
            "splits": len(data.splits),
            "sections": len(data.sections),
            "tests_passed": sum(s.tests_passed for s in data.sections),
            "tests_total": sum(s.tests_total for s in data.sections),
            "commits": len(data.commits),
            "decisions": sum(len(e.decisions) for e in data.decisions),
            "packages": len(data.dependencies),
        },
    }
    config_path = project_root / "shipwright_compliance_config.json"
    config_path.write_text(json.dumps(config, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    output = {
        "success": True,
        "artifacts": artifacts,
        "summary": config["summary"],
    }
    print(json.dumps(output, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
