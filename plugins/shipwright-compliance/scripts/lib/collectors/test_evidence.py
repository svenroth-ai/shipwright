"""Test-evidence-facing collectors: test results + test files + known failures.

* ``shipwright_test_results.json`` (and archived ``split_*_test_results.json``)
  feed the aggregated ``TestResults`` snapshot.
* ``tests/`` scan produces a file-name map (used by RTM coverage rendering).
* ``shipwright_known_failures.json`` lists pre-existing baseline failures so
  the dashboard never re-counts them as new regressions.

Iterate Campaign B (B2): split out of ``data_collector.py``.
"""

from __future__ import annotations

import json
from pathlib import Path

from ._types import KnownFailure, TestResults


def _parse_test_results_file(path: Path) -> TestResults | None:
    """Parse a single test results JSON file into a TestResults object."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None

    unit = data.get("unit", {})
    integration = data.get("integration", {})
    pgtap = data.get("pgtap", {})
    smoke = data.get("smoke", {})
    e2e = data.get("e2e", {})
    design_fidelity = data.get("design_fidelity", data.get("visual", {}))
    consistency = data.get("consistency", {})

    # Check for design-fidelity-report.json alongside the test results file (with fallback)
    design_fidelity_report_path = ""
    for report_name in ("design-fidelity-report.json", "visual-build-report.json"):
        report_candidate = path.parent / report_name
        if report_candidate.exists():
            design_fidelity_report_path = str(report_candidate)
            break

    return TestResults(
        schema_version=data.get("schema_version", 1),
        status=data.get("status", ""),
        timestamp=data.get("timestamp", ""),
        unit_passed=unit.get("passed", 0),
        unit_total=unit.get("total", 0),
        unit_duration_s=unit.get("duration_s", 0),
        integration_passed=integration.get("passed", 0),
        integration_total=integration.get("total", 0),
        integration_duration_s=integration.get("duration_s", 0),
        integration_skipped=integration.get("skipped", False),
        integration_skip_reason=integration.get("skip_reason", integration.get("reason", "")),
        pgtap_passed=pgtap.get("passed", 0),
        pgtap_total=pgtap.get("total", 0),
        pgtap_duration_s=pgtap.get("duration_s", 0),
        pgtap_skipped=pgtap.get("skipped", False),
        pgtap_skip_reason=pgtap.get("skip_reason", pgtap.get("reason", "")),
        smoke_status=smoke.get("status", ""),
        smoke_url=smoke.get("url", ""),
        smoke_response_ms=smoke.get("response_ms", 0),
        e2e_passed=e2e.get("passed", 0),
        e2e_total=e2e.get("total", 0),
        e2e_failures=e2e.get("failures", []),
        e2e_skipped=e2e.get("skipped", False),
        e2e_skip_reason=e2e.get("reason", ""),
        design_fidelity_passed=design_fidelity.get("passed", 0),
        design_fidelity_total=design_fidelity.get("total", 0),
        design_fidelity_skipped=design_fidelity.get("skipped", False),
        design_fidelity_skip_reason=design_fidelity.get("skip_reason", ""),
        design_fidelity_report_path=design_fidelity_report_path,
        consistency_passed=consistency.get("passed", 0),
        consistency_total=consistency.get("total", 0),
        consistency_skipped=consistency.get("skipped", False),
        consistency_skip_reason=consistency.get("skip_reason", ""),
    )


def collect_test_results(project_root: Path) -> TestResults | None:
    """Read and aggregate test results from current + archived split results.

    Reads split_*_test_results.json (archived) and shipwright_test_results.json
    (current), aggregating unit/e2e counts across all splits.
    """
    all_results: list[TestResults] = []

    # Archived split results
    for f in sorted(project_root.glob("split_*_test_results.json")):
        tr = _parse_test_results_file(f)
        if tr:
            all_results.append(tr)

    # Current results
    current = project_root / "shipwright_test_results.json"
    if current.exists():
        tr = _parse_test_results_file(current)
        if tr:
            all_results.append(tr)

    if not all_results:
        return None

    if len(all_results) == 1:
        return all_results[0]

    # Aggregate across splits
    return TestResults(
        schema_version=max(r.schema_version for r in all_results),
        status="pass" if all(r.status == "pass" for r in all_results) else "fail",
        timestamp=all_results[-1].timestamp,  # Most recent
        unit_passed=sum(r.unit_passed for r in all_results),
        unit_total=sum(r.unit_total for r in all_results),
        unit_duration_s=sum(r.unit_duration_s for r in all_results),
        integration_passed=sum(r.integration_passed for r in all_results),
        integration_total=sum(r.integration_total for r in all_results),
        integration_duration_s=sum(r.integration_duration_s for r in all_results),
        integration_skipped=all_results[-1].integration_skipped,
        integration_skip_reason=all_results[-1].integration_skip_reason,
        pgtap_passed=sum(r.pgtap_passed for r in all_results),
        pgtap_total=sum(r.pgtap_total for r in all_results),
        pgtap_duration_s=sum(r.pgtap_duration_s for r in all_results),
        pgtap_skipped=all_results[-1].pgtap_skipped,
        pgtap_skip_reason=all_results[-1].pgtap_skip_reason,
        smoke_status=all_results[-1].smoke_status,  # Latest split's smoke
        smoke_url=all_results[-1].smoke_url,
        smoke_response_ms=all_results[-1].smoke_response_ms,
        e2e_passed=sum(r.e2e_passed for r in all_results),
        e2e_total=sum(r.e2e_total for r in all_results),
        e2e_failures=[f for r in all_results for f in r.e2e_failures],
        e2e_skipped=all_results[-1].e2e_skipped,
        e2e_skip_reason=all_results[-1].e2e_skip_reason,
        design_fidelity_passed=sum(r.design_fidelity_passed for r in all_results),
        design_fidelity_total=sum(r.design_fidelity_total for r in all_results),
        design_fidelity_skipped=all_results[-1].design_fidelity_skipped,
        design_fidelity_skip_reason=all_results[-1].design_fidelity_skip_reason,
    )


def collect_test_files(project_root: Path) -> dict[str, list[str]]:
    """Scan tests/ directory and map test files to sections by path convention.

    Returns dict: section_name -> [relative test file paths].
    """
    test_dir = project_root / "tests"
    if not test_dir.exists():
        return {}

    file_map: dict[str, list[str]] = {}
    for test_file in test_dir.rglob("*.test.*"):
        rel_path = str(test_file.relative_to(project_root)).replace("\\", "/")
        # Use the file path as-is; grouping by section done at report level
        file_map.setdefault("_all", []).append(rel_path)

    return file_map


def collect_known_failures(project_root: Path) -> tuple[list[KnownFailure], int]:
    """Load known failures from shipwright_known_failures.json.

    Returns (failures_list, baseline_failure_count).
    """
    path = project_root / "shipwright_known_failures.json"
    if not path.exists():
        return [], 0
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return [], 0

    failures = [
        KnownFailure(
            test=f.get("test", ""),
            description=f.get("description", ""),
            ticket=f.get("ticket", ""),
            added=f.get("added", ""),
            count=f.get("count", 1),
        )
        for f in data.get("known_failures", [])
    ]
    baseline = data.get("baseline_failure_count", sum(f.count for f in failures))
    return failures, baseline
