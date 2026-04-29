#!/usr/bin/env python3
"""/shipwright-compliance detective audit entry point (plan v7 Option Z).

Usage:
    uv run run_audit.py --project-root <path> [--fix] [--only A,B,E] [--format md|json|both]

Called by ``skills/compliance/SKILL.md`` after Step 10. Standalone CLI so
users can invoke it outside the skill flow too (CI, ad-hoc debugging).

Step 3 lands the skeleton. Individual group checks register themselves
as Steps 4-8 ship.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Make sibling modules importable whether run as script or via uv.
_PLUGIN_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_ROOT))

from scripts.audit._registry import register_all  # noqa: E402
from scripts.audit.audit_detector import run_all  # noqa: E402
from scripts.audit.audit_report import render_markdown, write as write_report  # noqa: E402


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Detective audit for cross-artifact consistency.",
    )
    p.add_argument("--project-root", required=True,
                   help="Project root (directory with shipwright_run_config.json)")
    p.add_argument("--fix", action="store_true",
                   help="Enable auto-fix for Group E (per-doc regen).")
    p.add_argument("--only", default="",
                   help="Restrict to groups, comma-separated (A,B,C,D,E,F,G).")
    p.add_argument("--format", choices=["md", "json", "both"], default="both",
                   help="Output format for the report. Default: both.")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    project_root = Path(args.project_root).resolve()
    if not project_root.is_dir():
        print(json.dumps({"error": f"project_root does not exist: {project_root}"}),
              file=sys.stderr)
        return 2

    only = [g.strip() for g in args.only.split(",") if g.strip()] or None

    register_all()
    report = run_all(project_root, only=only)

    if report.import_gate_error:
        print(report.import_gate_error, file=sys.stderr)
        return 3

    # Step 9 rendering. ``--format both`` writes .shipwright/compliance/audit-report.md
    # AND shipwright_audit_report.json; ``--format md|json`` writes only
    # the named one. stdout always carries the JSON payload so automated
    # callers have a stable contract.
    want_md = args.format in ("md", "both")
    want_json = args.format in ("json", "both")
    written = write_report(report, project_root,
                           markdown=want_md, json_out=want_json)

    payload = report.to_dict()
    payload["written"] = {fmt: str(p.relative_to(project_root))
                          for fmt, p in written.items()}
    print(json.dumps(payload, indent=2))
    return 0 if not report.any_fail else 1


if __name__ == "__main__":
    sys.exit(main())
