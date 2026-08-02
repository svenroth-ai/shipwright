#!/usr/bin/env python3
"""Incremental compliance update — called by orchestrator after each phase.

Usage:
    uv run update_compliance.py --project-root <path> --phase <name>

Only regenerates reports affected by the completed phase.
"""

import argparse
import json
import os
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
    # An audit run changes the freshness disclosure carried by EVERY evidence
    # document (lib/audit_disclosure.py), not just the dashboard's section — so
    # the /shipwright-compliance flow regenerates all five. Without this the
    # documents keep saying "never run" until some later phase happens to touch
    # them, which is the exact lag this disclosure exists to remove.
    "compliance": ["rtm", "test_evidence", "change_history", "sbom", "dashboard"],
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


def _capture_source_dirty(project_root: Path, run_id: str | None) -> bool | None:
    """Dirtiness of the tree BEFORE this process writes anything (``trg-f5ae5371``).

    Must be called before the first generator runs: every generator rewrites a
    TRACKED document, so a measurement taken later reads ``true`` on a pristine
    tree — the withdrawn implementation this replaces.

    ``capture_dirty`` is first-call-wins and bound to the run id AND the tree, so
    when a parent producer already captured (``finalize_iterate`` appends to the
    tracked event log before spawning us) this INHERITS that earlier answer instead
    of measuring a tree the parent has already dirtied.

    The ``sys.path`` front-insert is **scoped to the import** and undone in the
    ``finally``, unlike the emitter's permanent one: this runs at ``main()`` entry,
    before every generator imports, and ``shared/scripts`` at front-precedence can
    shadow this plugin's own ``lib`` package (the reason
    ``collectors/_lib_loader.py`` exists). Leaving it in place would widen that
    hazard across the whole regen for no gain — the module is in ``sys.modules``
    after the first import either way (Stage-3 doubt D4).
    """
    shared = str(Path(__file__).resolve().parents[4] / "shared" / "scripts")
    inserted = shared not in sys.path
    if inserted:
        sys.path.insert(0, shared)
    try:
        from source_state_capture import capture_dirty  # noqa: PLC0415
        return capture_dirty(project_root, run_id)
    except Exception as exc:  # noqa: BLE001 — never block a compliance regen
        # Loud, because this is the one degradation nobody can see downstream: an
        # unknown `dirty` is OMITTED, and an absent field is indistinguishable from
        # an event that predates it. A permanently broken import here would
        # otherwise be invisible forever.
        print(f"update_compliance: source-state capture failed: {exc}",
              file=sys.stderr)
        return None
    finally:
        if inserted:
            try:
                sys.path.remove(shared)
            except ValueError:  # something else already removed it
                pass


def main() -> int:
    parser = argparse.ArgumentParser(description="Incremental compliance update")
    parser.add_argument("--project-root", required=True, help="Project root directory")
    parser.add_argument("--phase", help="Completed phase name (write-mode)")
    parser.add_argument("--check", action="store_true",
                        help="Staleness-only diff; writes nothing. Implies --phase is optional.")
    parser.add_argument("--run-id", default=None,
                        help="Run this regen belongs to. Binds the source-state capture "
                             "so a parent producer's pre-write measurement is inherited "
                             "rather than re-taken. Falls back to SHIPWRIGHT_RUN_ID.")
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()

    if args.check:
        output = _run_check_mode(project_root)
        print(json.dumps(output, indent=2))
        return 0

    if not args.phase:
        parser.error("--phase is required unless --check is set")

    phase = args.phase

    # BEFORE anything is written. An explicit --run-id beats the ambient env var:
    # a caller that names the run knows better than a variable that may have been
    # exported by an unrelated, longer-lived shell.
    run_id = (args.run_id if args.run_id is not None
              else os.environ.get("SHIPWRIGHT_RUN_ID") or None)
    source_dirty = _capture_source_dirty(project_root, run_id)

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
    generator_errors: list[dict] = []
    for report_name in reports_to_update:
        gen_fn = GENERATORS.get(report_name)
        if gen_fn:
            # One collector refusing to write MUST NOT dark the rest of the dashboard.
            # The generators run in list order, so an uncaught raise from an early one
            # (e.g. test_links refusing to publish an incomplete manifest when a spec
            # declares an FR id twice) would abort the loop before change_history, sbom
            # and dashboard were written — an adopter would get a bare traceback, exit 1,
            # no JSON, and no compliance artifacts at all for an authoring defect in one
            # spec. Record the failure, keep going, and report it in the result payload
            # so it is loud without being fatal to everything downstream.
            try:
                path = gen_fn(project_root, data)
            except Exception as exc:  # noqa: BLE001 — one report's failure is not all reports'
                generator_errors.append({
                    "report": report_name,
                    "error": type(exc).__name__,
                    "detail": str(exc),
                })
                continue
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
                    grade_snapshot_result = emit_grade_snapshot(
                        data, dirty=source_dirty)
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
        "success": not generator_errors,
        "phase": phase,
        "updated_reports": updated,
    }
    if generator_errors:
        # Reported, and non-zero on exit, but only AFTER every other report was
        # given its chance to write — a defect in one spec must not leave the
        # operator with no dashboard at all.
        output["generator_errors"] = generator_errors
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
    return 1 if generator_errors else 0


if __name__ == "__main__":
    sys.exit(main())
