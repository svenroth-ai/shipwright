#!/usr/bin/env python3
"""/shipwright-compliance detective audit entry point (plan v7 Option Z).

Usage:
    uv run run_audit.py --project-root <path> [--fix] [--only A,B,E] [--format md|json|both]

Called by ``skills/compliance/SKILL.md`` after Step 10. Standalone CLI so
users can invoke it outside the skill flow too (CI, ad-hoc debugging).

Plan v7 status: Sub-Iterate A wired Groups A + D, Sub-Iterate B wired
Group B, Sub-Iterate C wired Groups E + G plus Step 13 default-config
tuning. The full A..G coverage is now active. ``--fix`` rewrites stale
compliance docs in place via Group E (no commit — caller decides).
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
from scripts.audit.audit_report import write as write_report  # noqa: E402
from scripts.lib.audit_disclosure import SCOPE_FULL, record_audit_run  # noqa: E402


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
    report = run_all(project_root, only=only, fix=args.fix)

    if report.import_gate_error:
        print(report.import_gate_error, file=sys.stderr)
        return 3

    # Step 9 rendering. ``--format both`` writes .shipwright/compliance/audit-report.md
    # AND .shipwright/compliance/audit-report.json (both gitignored); ``--format
    # md|json`` writes only the named one. stdout always carries the JSON payload
    # so automated callers have a stable contract.
    want_md = args.format in ("md", "both")
    want_json = args.format in ("json", "both")
    written = write_report(report, project_root,
                           markdown=want_md, json_out=want_json)

    # Nothing schedules this audit — no cron, no workflow, no hook — so it is
    # the only thing that can say it ran. Record that durably (tracked state,
    # unlike the gitignored reports above) so every compliance document can
    # disclose how far back the last cross-check reaches. A partial ``--only``
    # run is recorded as partial and can never be read as a full check.
    # Best-effort by contract: this exit code answers "is the project
    # consistent?", and bookkeeping must never change that answer.
    if not report.groups_run:
        # Nothing ran, so nothing was checked — usually a typo'd --only, whose
        # unknown letters land in groups_skipped. Storing this would freshen
        # every document's disclosure on the strength of an empty run AND write
        # `verdict: pass` to describe it, displacing a real earlier record. A
        # stored record has to keep meaning "this audit checked something".
        recorded = {"recorded": False, "reason": "no_group_ran"}
        requested = ", ".join(letter for letter, _ in report.groups_skipped)
        print(
            "run_audit: WARNING — no audit group ran"
            f"{f' (requested: {requested})' if requested else ''}, so nothing "
            "was checked and nothing was recorded. Check --only.",
            file=sys.stderr,
        )
    else:
        try:
            recorded = record_audit_run(
                project_root,
                statuses=[f.status for f in report.findings],
                any_fail=bool(report.any_fail),
                scope=",".join(only) if only else SCOPE_FULL,
            )
        except Exception as exc:  # noqa: BLE001 — never change the audit's verdict
            recorded = {"recorded": False, "reason": str(exc)}
        if not recorded.get("recorded"):
            # Loud, but not fatal. A silent failure here leaves every compliance
            # document claiming the audit never ran, indefinitely — the operator
            # has to know the durability half did not happen.
            print(
                "run_audit: WARNING — the run completed but could not be "
                f"recorded ({recorded.get('reason')}); compliance documents "
                "will not disclose it. Fix the config and re-run.",
                file=sys.stderr,
            )

    payload = report.to_dict()
    payload["last_audit_recorded"] = recorded
    payload["written"] = {fmt: str(p.relative_to(project_root))
                          for fmt, p in written.items()}
    print(json.dumps(payload, indent=2))
    return 0 if not report.any_fail else 1


if __name__ == "__main__":
    sys.exit(main())
