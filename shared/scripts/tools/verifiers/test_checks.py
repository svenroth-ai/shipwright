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
import sys
from pathlib import Path

# The accepted-baseline reader is shared with the compliance audit. It lives at
# ``shared/scripts/`` top level (not under a ``lib/`` package) so importing it
# can never shadow a plugin's own ``scripts/lib`` namespace — ADR-045.
_SHARED_SCRIPTS = Path(__file__).resolve().parents[2]
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

from known_failures import (  # noqa: E402
    KNOWN_FAILURES_NAME,
    genuine_failure_count,
    has_exact_failure_count,
    load_accepted_baseline,
)

from .common import (
    CheckResult,
    Severity,
    check_adr_ids_sequential,
    check_adr_status_valid,
    check_adr_supersession_exists,
    check_c1_phase_event_recorded,
    check_c2_dashboard_reflects_phase,
    check_phase_history_has_run,
)
from .handoff_freshness import check_c3_session_handoff_fresh_after_phase


# ---------------------------------------------------------------------------
# Phase-own
# ---------------------------------------------------------------------------

def check_test_results_file_fresh(project_root: Path) -> CheckResult:
    """``shipwright_test_results.json`` must exist and have a populated
    ``unit`` layer. The other layers (integration / e2e / smoke) are
    optional per profile, but unit is always expected.

    Reads the same accepted-baseline list the audit phase reads
    (``shipwright_known_failures.json``), so an onboarded project's inherited
    failures are not reported here as a failing run while the audit reports the
    same run as within baseline
    (iterate-2026-07-27-test-phase-record-honesty, FR-01.06).

    The baseline is an **aggregate allowance** — it says how many failures were
    declared, not which. The detail line says so rather than claiming these
    particular failures are the accepted ones.
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
    if not isinstance(passed, int):
        passed = 0

    # A skipped test is not a failure. Prefer the layer's own `failed` count;
    # fall back to the gap minus skips; fall back again to the bare gap.
    exact = has_exact_failure_count(unit.get("failed"), unit.get("skipped"))
    failures = genuine_failure_count(
        passed=passed,
        total=total,
        failed=unit.get("failed"),
        skipped=unit.get("skipped"),
    )
    if failures <= 0:
        return CheckResult(name, True, f"unit {passed}/{total} passed")

    baseline = load_accepted_baseline(project_root)
    declared = baseline.baseline_failure_count
    unreadable = " — accepted-failure list unreadable" if baseline.malformed else ""

    # The aggregate allowance is charity for an un-broken-down gap only. Where
    # the layer counted its failures exactly, the allowance does not apply —
    # the audit made that call deliberately (`tests_block.progression_result`,
    # pinned by `test_explicit_residual_ignores_baseline_charity`), and the two
    # must agree. Acceptance of an exactly-counted failure is decided per
    # failure by identity in the phase report, not by arithmetic here.
    if not exact and declared > 0 and failures <= declared:
        return CheckResult(
            name, True,
            f"unit {passed}/{total} passed; gap of {failures} within the "
            f"declared baseline of {declared} ({KNOWN_FAILURES_NAME}) — an "
            f"aggregate allowance over an un-broken-down gap, not a per-failure "
            f"acceptance",
        )

    if declared > 0:
        detail = (
            f"unit.passed={passed}/{total}: {failures} failing, "
            f"{declared} declared in the baseline"
        )
        if exact:
            detail += (
                " — an exactly-counted failure is not waived by a count; "
                "report which of them are known-and-accepted by name"
            )
        else:
            detail += f", {failures - declared} beyond it"
    else:
        detail = f"unit.passed={passed}/{total} ({failures} tests failing){unreadable}"

    return CheckResult(name, False, detail, severity=Severity.WARNING.value)


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
    results.append(check_c3_session_handoff_fresh_after_phase(project_root, "test", run_id=run_id))

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
