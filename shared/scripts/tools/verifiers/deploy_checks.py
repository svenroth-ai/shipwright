"""Deploy-phase verifier checks.

Iterate 12.4 brings the ``shipwright-deploy`` plugin to Minimum Phase
Completion Canon coverage at C1/C2/C3 only:

- **C4 skipped**: deployment is execution — the architectural
  decision was made upstream in plan.
- **C5 skipped**: deployment is operational history
  (``events.jsonl`` + ``phase_history``), not product change. The
  release narrative belongs to the changelog plugin's prepended
  ``## [vX.Y.Z]`` block; adding a deploy bullet to ``[Unreleased]``
  would duplicate and pollute the next version's notes.

Phase-own:

- ``check_test_gate_passed`` — pre-condition: the upstream test phase
  must have produced green results. Mirrors the legacy
  ``_validate_test`` unit gate so deploy_checks can stand alone.
"""

from __future__ import annotations

import json
from pathlib import Path

from .common import (
    CheckResult,
    Severity,
    check_adr_ids_sequential,
    check_adr_status_valid,
    check_adr_supersession_exists,
    check_c1_phase_event_recorded,
    check_c2_dashboard_reflects_phase,
    check_c3_session_handoff_fresh_after_phase,
    check_phase_history_has_run,
)


# ---------------------------------------------------------------------------
# Phase-own
# ---------------------------------------------------------------------------

def check_test_gate_passed(project_root: Path) -> CheckResult:
    """The test phase must have produced ``shipwright_test_results.json``
    with a green unit layer before deploy can run. Mirrors
    ``_validate_test``'s unit gate so the deploy verifier can stand
    alone without importing phase_validators.
    """
    name = "test gate: unit tests passed upstream"
    path = project_root / "shipwright_test_results.json"
    if not path.exists():
        return CheckResult(
            name, False,
            "shipwright_test_results.json missing — test phase never completed",
        )
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return CheckResult(name, False, f"malformed test results: {exc}")
    unit = data.get("unit") or {}
    total = unit.get("total", 0)
    passed = unit.get("passed", 0)
    if not isinstance(total, int) or total <= 0:
        return CheckResult(
            name, False,
            f"unit.total={total}, expected >0 (deploy blocked: no tests ran)",
        )
    if not isinstance(passed, int) or passed < total:
        return CheckResult(
            name, False,
            f"unit {passed}/{total} (deploy blocked: tests failing)",
        )
    smoke = data.get("smoke") or {}
    if smoke.get("status") == "fail":
        return CheckResult(
            name, False,
            "smoke test failed upstream — deploy should have been blocked",
        )
    return CheckResult(name, True, f"unit {passed}/{total} passed, smoke OK")


# ---------------------------------------------------------------------------
# Canon dispatcher
# ---------------------------------------------------------------------------

def run_deploy_checks(
    project_root: Path,
    *,
    run_id: str = "",
) -> list[CheckResult]:
    """Run the full deploy-phase verifier suite in stable order."""
    results: list[CheckResult] = []

    results.append(check_test_gate_passed(project_root))

    # Canon (C4 + C5 skipped)
    results.append(check_c1_phase_event_recorded(project_root, "deploy"))
    results.append(check_c2_dashboard_reflects_phase(project_root, "deploy"))
    results.append(check_c3_session_handoff_fresh_after_phase(project_root, "deploy"))

    # Phase history
    results.append(check_phase_history_has_run(project_root, "deploy", run_id))

    # ADR integrity
    results.append(check_adr_ids_sequential(project_root))
    results.append(check_adr_status_valid(project_root))
    results.append(check_adr_supersession_exists(project_root))

    return results


def run_all_checks(project_root: Path, run_id: str = "") -> list[CheckResult]:
    return run_deploy_checks(project_root, run_id=run_id)


__all__ = [
    "Severity",
    "check_test_gate_passed",
    "run_all_checks",
    "run_deploy_checks",
]
