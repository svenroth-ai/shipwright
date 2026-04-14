"""Test-phase verifier checks.

Iterate 12.4 brings the ``shipwright-test`` plugin to Minimum Phase
Completion Canon coverage at C1/C2/C3 only. Both LLM reviewers flagged
**C4 and C5 as CRITICAL skips**:

- **C4 skipped**: test runs are events, not architectural decisions.
  Adding a routine ADR per test run would pollute ``decision_log.md``.
- **C5 skipped**: test results belong in ``shipwright_test_results.json``,
  not CHANGELOG. Appending to ``[Unreleased]`` per run would spam the
  release notes.

Phase-own:

- ``check_test_results_file_fresh`` — ``shipwright_test_results.json``
  exists and has ``unit`` layer with non-zero total. ERROR.

Plus standard ``phase_history`` run-id check and ADR integrity helpers
from ``common.py``.
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

def check_test_results_file_fresh(project_root: Path) -> CheckResult:
    """``shipwright_test_results.json`` must exist and have a populated
    ``unit`` layer. The other layers (integration / e2e / smoke) are
    optional per profile, but unit is always expected.
    """
    name = "test_results unit layer populated"
    path = project_root / "shipwright_test_results.json"
    if not path.exists():
        return CheckResult(name, False, "shipwright_test_results.json missing")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return CheckResult(name, False, f"malformed results file: {exc}")
    unit = data.get("unit") or {}
    total = unit.get("total", 0)
    if not isinstance(total, int) or total <= 0:
        return CheckResult(
            name, False,
            f"unit.total={total}, expected >0 (were unit tests executed?)",
        )
    passed = unit.get("passed", 0)
    if not isinstance(passed, int) or passed < total:
        return CheckResult(
            name, False,
            f"unit.passed={passed}/{total} (tests failing)",
            severity=Severity.WARNING.value,
        )
    return CheckResult(name, True, f"unit {passed}/{total} passed")


# ---------------------------------------------------------------------------
# Canon dispatcher
# ---------------------------------------------------------------------------

def run_test_checks(
    project_root: Path,
    *,
    run_id: str = "",
) -> list[CheckResult]:
    """Run the full test-phase verifier suite in stable order."""
    results: list[CheckResult] = []

    results.append(check_test_results_file_fresh(project_root))

    # Canon (C4 and C5 skipped by policy)
    results.append(check_c1_phase_event_recorded(project_root, "test"))
    results.append(check_c2_dashboard_reflects_phase(project_root, "test"))
    results.append(check_c3_session_handoff_fresh_after_phase(project_root, "test"))

    # Phase history
    results.append(check_phase_history_has_run(project_root, "test", run_id))

    # ADR integrity
    results.append(check_adr_ids_sequential(project_root))
    results.append(check_adr_status_valid(project_root))
    results.append(check_adr_supersession_exists(project_root))

    return results


def run_all_checks(project_root: Path, run_id: str = "") -> list[CheckResult]:
    return run_test_checks(project_root, run_id=run_id)


__all__ = [
    "Severity",
    "check_test_results_file_fresh",
    "run_all_checks",
    "run_test_checks",
]
