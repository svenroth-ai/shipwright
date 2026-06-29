"""Dashboard 'Iterate tests passing' row excludes test-exempt changes (F2).

Pins the row-level wiring (denominator + wording) so a future refactor can't
silently revert to counting every iterate event. The classification logic itself
is unit-tested in test_traceability.py::TestIterateTestCoverage. Lives in its own
file because test_compliance_report.py is a grandfathered (>300 LOC) entry that
the anti-ratchet gate forbids growing.
"""

from __future__ import annotations

from pathlib import Path

from scripts.lib.compliance_report import generate
from scripts.lib.data_collector import ComplianceData, WorkEvent


def _data(project_root: Path, work_events: list[WorkEvent]) -> ComplianceData:
    return ComplianceData(
        project_root=project_root,
        configs={"run": {"profile": "test", "scope": "library"}},
        work_events=work_events,
        timestamp="2026-06-29T00:00:00Z",
    )


def test_iterate_tests_row_excludes_exempt_changes(tmp_path: Path) -> None:
    events = [
        # Testable feature work WITH tests → counts on both sides.
        WorkEvent(id="e1", timestamp="2026-06-01T00:00:00Z", source="iterate",
                  affected_frs=["FR-01.01"], spec_impact="add",
                  tests_passed=5, tests_total=5),
        # Testable change WITHOUT tests → residual deficit (honest WARN).
        WorkEvent(id="e2", timestamp="2026-06-02T00:00:00Z", source="iterate",
                  affected_frs=["FR-01.02"], spec_impact="modify", tests_total=0),
        # Behavior-preserving no-FR docs/compliance → exempt, dropped from BOTH.
        WorkEvent(id="e3", timestamp="2026-06-03T00:00:00Z", source="iterate",
                  change_type="docs", none_reason="readme", spec_impact="none"),
        WorkEvent(id="e4", timestamp="2026-06-04T00:00:00Z", source="iterate",
                  change_type="compliance", none_reason="regen", spec_impact="none"),
    ]
    md = generate(_data(tmp_path, events))
    # 1 tested of 2 testable (the two exempt events are excluded entirely) — the
    # denominator is 2, not the 4 raw iterate events.
    assert "| Iterate tests passing | 1/2 testable changes tested | WARN |" in md
    assert "1 testable change(s) without tests" in md


def test_iterate_tests_row_all_exempt_is_pass(tmp_path: Path) -> None:
    events = [
        WorkEvent(id="e1", timestamp="2026-06-01T00:00:00Z", source="iterate",
                  change_type="tooling", none_reason="ci", spec_impact="none"),
    ]
    md = generate(_data(tmp_path, events))
    # All iterate work is test-exempt → 0/0, PASS (no deficit).
    assert "| Iterate tests passing | 0/0 testable changes tested | PASS |" in md
