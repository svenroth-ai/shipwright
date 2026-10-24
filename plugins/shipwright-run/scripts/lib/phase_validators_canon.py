"""Canon verifier bridge for the phase validators (extracted from ``phase_validators``)."""

from __future__ import annotations

from pathlib import Path


def _run_canon_checks(
    phase: str,
    project_root: Path,
    issues: list[dict[str, str]],
) -> None:
    """Shared canon verifier bridge used by every iterate-12 phase
    validator (project in 12.1; design + plan in 12.2).

    Dispatches to the matching ``tools.verifiers.<phase>_checks``
    module lazily so the import never fires in older test suites that
    stubbed ``phase_validators`` without these files on the path.
    Appends ask-level issues for every ERROR-severity result and
    inform-level issues for every WARNING. SKIPPED and green results
    are ignored.
    """
    try:
        from tools.verifiers.common import Severity
        if phase == "project":
            from tools.verifiers.project_checks import run_project_checks as _run
        elif phase == "design":
            from tools.verifiers.design_checks import run_design_checks as _run
        elif phase == "plan":
            from tools.verifiers.plan_checks import run_plan_checks as _run
        elif phase == "build":
            from tools.verifiers.build_checks import run_build_checks as _run
        elif phase == "test":
            from tools.verifiers.test_checks import run_test_checks as _run
        elif phase == "changelog":
            from tools.verifiers.changelog_checks import run_changelog_checks as _run
        elif phase == "deploy":
            from tools.verifiers.deploy_checks import run_deploy_checks as _run
        else:
            return
    except ImportError:
        return

    import os
    run_id = os.environ.get("SHIPWRIGHT_RUN_ID", "")
    for r in _run(project_root, run_id=run_id):
        if r.is_skipped or r.ok:
            continue
        severity = "ask" if r.severity == Severity.ERROR.value else "inform"
        issues.append({
            "severity": severity,
            "message": f"[canon] {r.name}: {r.detail}",
        })
