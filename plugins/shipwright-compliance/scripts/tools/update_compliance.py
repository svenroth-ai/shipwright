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

from scripts.lib.audit_freshness import mark_audit_report_stale
from scripts.lib.data_collector import collect_all
from scripts.lib.rtm_generator import generate_file as generate_rtm
from scripts.lib.test_evidence import (
    emit_test_failure_triage,
    generate_file as generate_test_evidence,
)
from scripts.lib.change_history import generate_file as generate_change_history
from scripts.lib.collectors.test_links import generate_file as generate_test_links
from scripts.lib.compliance_report import generate_file as generate_dashboard
from scripts.lib._grade_snapshot import emit_grade_snapshot
from scripts.lib.sbom_generator import (
    emit_undeclared_triage,
    generate_file as generate_sbom,
)

# Phase -> which reports to regenerate.
# ``test_links`` (the requirement->test traceability manifest, campaign TT1) rides
# with the FR/test-affecting phases: FRs change on project/plan, the tag↔test join
# changes on build/test/changelog/iterate. adopt (the baseline) is wired in TT7.
PHASE_REPORTS = {
    "project": ["rtm", "test_links", "dashboard"],
    "design": ["dashboard"],
    "plan": ["rtm", "test_links", "dashboard"],
    "compliance": ["dashboard"],
    "build": ["rtm", "test_evidence", "test_links", "change_history", "sbom", "dashboard"],
    "test": ["test_evidence", "test_links", "dashboard"],
    "deploy": ["dashboard"],
    "changelog": ["rtm", "test_evidence", "test_links", "change_history", "sbom", "dashboard"],
    "iterate": ["rtm", "test_evidence", "test_links", "change_history", "sbom", "dashboard"],
    # iterate-2026-05-23-security-adopt-compliance-snapshots:
    # adopt establishes the initial baseline → all 5 docs.
    # security pipeline finalize touches dashboard/test_evidence/change_history/sbom
    # but NOT rtm — security work doesn't add/modify FRs.
    # traceability TT7: adopt seeds the initial test-traceability manifest too — the
    # backfill step (seed_traceability_baseline.py) tags existing tests just BEFORE Step F,
    # so this collector emits the baseline RTM link from those tags at onboarding.
    "adopt": ["rtm", "test_evidence", "test_links", "change_history", "sbom", "dashboard"],
    "security": ["dashboard", "test_evidence", "change_history", "sbom"],
}

GENERATORS = {
    "rtm": generate_rtm,
    "test_evidence": generate_test_evidence,
    "test_links": generate_test_links,
    "change_history": generate_change_history,
    "dashboard": generate_dashboard,
    "sbom": generate_sbom,
}


def _run_check_mode(project_root: Path) -> dict:
    """Snapshot-provenance check mode for /shipwright-compliance.

    Post-iterate-2026-05-23: compares on-disk MDs to the last
    iterate-finalize snapshot (located by ``Run-ID:`` + diff-filter on
    ``.shipwright/compliance/``). Writes nothing — operator runs the
    write-mode (``--phase ...``) separately if they want to refresh.
    """
    from scripts.audit.audit_staleness import check_staleness

    report = check_staleness(project_root)
    return {
        "mode": "check",
        "success": True,
        "staleness": report.to_dict(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Incremental compliance update")
    parser.add_argument("--project-root", required=True, help="Project root directory")
    parser.add_argument("--phase", help="Completed phase name (write-mode)")
    parser.add_argument("--check", action="store_true",
                        help="Staleness-only diff; writes nothing. Implies --phase is optional.")
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()

    if args.check:
        output = _run_check_mode(project_root)
        print(json.dumps(output, indent=2))
        return 0

    if not args.phase:
        parser.error("--phase is required unless --check is set")

    phase = args.phase

    reports_to_update = PHASE_REPORTS.get(phase, ["dashboard"])

    # Collect data once
    data = collect_all(project_root)

    # AR-10: refresh the committed CI-security summary from the latest
    # security.yml run BEFORE the dashboard reads it. Best-effort + fail-soft
    # (gh missing / offline / no fresh run → leaves the existing summary
    # untouched), so it never blocks a regen and never fabricates a scan.
    ci_security_result: dict | None = None
    if "dashboard" in reports_to_update:
        try:
            from scripts.tools.refresh_ci_security import refresh_ci_security
            ci_security_result = refresh_ci_security(project_root)
        except Exception as exc:  # noqa: BLE001 — never block compliance regen
            ci_security_result = {"status": "error", "reason": str(exc)}

    updated = []
    sbom_triage_result: dict | None = None
    test_evidence_triage_result: dict | None = None
    grade_snapshot_result: dict | None = None
    for report_name in reports_to_update:
        gen_fn = GENERATORS.get(report_name)
        if gen_fn:
            path = gen_fn(project_root, data)
            updated.append(str(path.relative_to(project_root)))
            # Iterate B.2 (ADR-056): when the SBOM is regenerated, emit
            # one ``source="sbom"`` triage item per workspace that still
            # has undeclared licenses, and auto-dismiss workspaces that
            # are now clean. Best-effort: failures here do not abort
            # compliance generation.
            if report_name == "sbom":
                try:
                    sbom_triage_result = emit_undeclared_triage(project_root)
                except Exception as exc:  # noqa: BLE001
                    sbom_triage_result = {
                        "appended": 0, "dismissed": 0, "clusters": 0,
                        "error": str(exc),
                    }
            # Iterate B.3 (ADR-057): when test-evidence is regenerated,
            # emit one ``source="test-evidence"`` triage item per
            # failing layer in the latest test_run event, and
            # auto-dismiss layers that are now green. Same best-effort
            # contract as SBOM.
            elif report_name == "test_evidence":
                try:
                    test_evidence_triage_result = emit_test_failure_triage(project_root)
                except Exception as exc:  # noqa: BLE001
                    test_evidence_triage_result = {
                        "appended": 0, "dismissed": 0, "error": str(exc),
                    }
            # M-Pre-3: when the dashboard (Control Grade) is regenerated, append
            # one grade_snapshot event to the durable event log so the WebUI
            # Ship's-Log can trend the grade. Same best-effort contract — a
            # failure here never aborts the compliance regen.
            elif report_name == "dashboard":
                try:
                    grade_snapshot_result = emit_grade_snapshot(data)
                except Exception as exc:  # noqa: BLE001
                    grade_snapshot_result = {"appended": 0, "error": str(exc)}

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

    # Routine regens refresh the dashboard et al. but NOT the detective
    # audit-report.md (only /shipwright-compliance → run_audit.py writes it), so a
    # month-old audit can sit on disk looking current. Stamp a staleness banner so
    # it announces it's stale. Skip the /shipwright-compliance flow itself
    # (phase == "compliance"), which re-runs the audit and fully overwrites the
    # file. Best-effort + fail-soft: never block a regen.
    audit_staleness_result: dict | None = None
    if phase != "compliance":
        try:
            audit_staleness_result = mark_audit_report_stale(project_root)
        except Exception as exc:  # noqa: BLE001 — never block compliance regen
            audit_staleness_result = {"stamped": False, "reason": str(exc)}

    output = {
        "success": True,
        "phase": phase,
        "updated_reports": updated,
    }
    if audit_staleness_result is not None:
        output["audit_staleness"] = audit_staleness_result
    if sbom_triage_result is not None:
        output["sbom_triage"] = sbom_triage_result
    if test_evidence_triage_result is not None:
        output["test_evidence_triage"] = test_evidence_triage_result
    if grade_snapshot_result is not None:
        output["grade_snapshot"] = grade_snapshot_result
    if ci_security_result is not None:
        output["ci_security"] = ci_security_result
    print(json.dumps(output, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
