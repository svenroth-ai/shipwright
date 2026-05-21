"""Tests for compliance_report.py (dashboard)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from scripts.lib.data_collector import (
    ComplianceData,
    DependencyInfo,
    WorkEvent,
    collect_all,
)
from scripts.lib.compliance_report import generate, generate_file

# Append triage items via the shared producer so test fixtures match
# production wire-shape (B0 schema).
_REPO_ROOT = Path(__file__).resolve().parents[3]
_SHARED_SCRIPTS = _REPO_ROOT / "shared" / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))
from triage import append_triage_item  # noqa: E402


class TestGenerate:
    def test_produces_dashboard(self, project_root: Path):
        data = collect_all(project_root)
        result = generate(data)
        assert "# Compliance Dashboard" in result

    def test_no_pipeline_status_diagram(self, project_root: Path):
        """Pipeline status lives in delivery dashboard, not compliance."""
        data = collect_all(project_root)
        result = generate(data)
        assert "## Pipeline Status" not in result

    def test_quality_indicators(self, project_root: Path):
        data = collect_all(project_root)
        result = generate(data)
        assert "## Quality Indicators" in result
        assert "| All unit tests passing | 16/16 | PASS |" in result
        assert "| Copyleft license risk | 0 | PASS |" in result

    def test_compliance_artifacts_links(self, project_root: Path):
        data = collect_all(project_root)
        result = generate(data)
        assert "./traceability-matrix.md" in result
        assert "./test-evidence.md" in result
        assert "./change-history.md" in result
        assert "./sbom.md" in result

    def test_no_traceability_overview(self, project_root: Path):
        data = collect_all(project_root)
        result = generate(data)
        assert "## Traceability Overview" not in result

    def test_no_cost_summary(self, project_root: Path):
        data = collect_all(project_root)
        result = generate(data)
        assert "## Cost Summary" not in result

    def test_copyleft_detection(self):
        data = ComplianceData(project_root=Path("."))
        data.timestamp = "2026-03-21T14:00:00Z"
        data.configs = {"run": {"profile": "test", "scope": "full_app"}}
        data.dependencies = [
            DependencyInfo("react", "19.0.0", "runtime", "MIT"),
            DependencyInfo("gpl-pkg", "1.0.0", "runtime", "GPL-3.0"),
        ]
        result = generate(data)
        assert "| Copyleft license risk | 1 | WARN |" in result

    def test_empty_data(self, empty_project_root: Path):
        data = collect_all(empty_project_root)
        result = generate(data)
        assert "# Compliance Dashboard" in result
        assert "| All sections completed | 0/0 | WARN |" in result


class TestGenerateFile:
    def test_writes_file(self, project_root: Path):
        data = collect_all(project_root)
        path = generate_file(project_root, data)
        assert path.exists()
        assert path.name == "dashboard.md"
        content = path.read_text(encoding="utf-8")
        assert "# Compliance Dashboard" in content


# ---------------------------------------------------------------------------
# Iterate B.1 (2026-05-21) — mode-aware indicators + Why-warn + Triage open
# ---------------------------------------------------------------------------


def _build_event_data(
    *,
    project_root: Path,
    adopted: bool,
    work_events: list[WorkEvent] | None = None,
    phase_events: list[dict] | None = None,
) -> ComplianceData:
    """Construct a ComplianceData with work_events present (the event-based
    quality-indicator path that B.1 changes)."""
    run_config = {"profile": "test", "scope": "full_app"}
    if adopted:
        run_config["adoption"] = {
            "adopted_at": "2026-05-02T00:00:00Z",
            "commit_at_adoption": "deadbeef",
        }
    data = ComplianceData(project_root=project_root)
    data.timestamp = "2026-05-21T00:00:00Z"
    data.configs = {"run": run_config}
    data.work_events = work_events or [
        WorkEvent(
            id="evt-1", timestamp="2026-05-20T10:00:00Z", source="iterate",
            tests_passed=12, tests_total=12, intent="feature",
            description="add x",
        ),
    ]
    data.phase_events = phase_events or []
    return data


class TestAdoptedModeIndicators:
    """B.1 — adopted projects show n/a for pipeline phases and HIDE
    build-section indicators that are structurally inapplicable."""

    def test_adopted_pipeline_row_is_na(self, tmp_path: Path):
        data = _build_event_data(project_root=tmp_path, adopted=True)
        result = generate(data)
        assert "| Pipeline phases completed | n/a (adopted) | INFO |" in result
        # No fake-WARN row
        assert "Pipeline phases completed | 0/7" not in result
        assert "Pipeline phases completed | 1/7" not in result

    def test_adopted_hides_build_sections_row(self, tmp_path: Path):
        data = _build_event_data(project_root=tmp_path, adopted=True)
        result = generate(data)
        # Both rows that are structurally N/A for adopted projects:
        assert "Work events (build)" not in result
        assert "All sections reviewed" not in result

    def test_greenfield_keeps_pipeline_and_section_rows(self, tmp_path: Path):
        data = _build_event_data(project_root=tmp_path, adopted=False)
        result = generate(data)
        assert "Pipeline phases completed" in result
        assert "Work events (build)" in result
        assert "All sections reviewed" in result
        assert "n/a (adopted)" not in result


class TestWhyWarnColumn:
    """B.1 — every quality-indicator table has a 'Why warn?' 4th column;
    WARN rows carry a one-line diagnostic pointer, others stay empty."""

    def test_header_has_why_warn_column(self, tmp_path: Path):
        data = _build_event_data(project_root=tmp_path, adopted=False)
        result = generate(data)
        assert "| Metric | Value | Status | Why warn? |" in result
        assert "|--------|-------|--------|-----------|" in result

    def test_failing_tests_carry_diagnostic(self, tmp_path: Path):
        events = [
            WorkEvent(
                id="evt-1", timestamp="2026-05-20T10:00:00Z", source="iterate",
                tests_passed=8, tests_total=12, intent="feature",
            ),
        ]
        data = _build_event_data(
            project_root=tmp_path, adopted=False, work_events=events,
        )
        result = generate(data)
        # The Why-warn cell mentions where to look
        assert "4/12 failing" in result
        assert "test-evidence.md" in result

    def test_passing_tests_have_empty_diagnostic(self, tmp_path: Path):
        data = _build_event_data(project_root=tmp_path, adopted=False)
        result = generate(data)
        # The All-unit-tests row ends with PASS + empty cell + closing bar.
        # Look for the exact pattern.
        assert "| All unit tests passing | 12/12 | PASS |  |" in result


class TestTriageOpenIndicator:
    """B.1 — new 'Triage open' indicator on every dashboard."""

    def test_zero_open_items_passes(self, tmp_path: Path):
        data = _build_event_data(project_root=tmp_path, adopted=False)
        result = generate(data)
        assert "| Triage open |" in result
        assert "| Triage open | 0 open | PASS |  |" in result

    def test_signal_items_warn_with_link(self, tmp_path: Path):
        # Seed real triage items via the shared producer so the schema
        # contract is exercised end-to-end.
        append_triage_item(
            tmp_path, source="phaseQuality", severity="high", kind="bug",
            title="t", detail="d",
        )
        append_triage_item(
            tmp_path, source="drift", severity="medium", kind="maintenance",
            title="t2", detail="d2",
        )
        data = _build_event_data(project_root=tmp_path, adopted=False)
        result = generate(data)
        assert "| Triage open | 2 open | WARN |" in result
        assert "../agent_docs/triage_inbox.md" in result

    def test_info_only_items_pass_with_info_count(self, tmp_path: Path):
        append_triage_item(
            tmp_path, source="drift", severity="info", kind="maintenance",
            title="info-1", detail="d",
        )
        append_triage_item(
            tmp_path, source="drift", severity="info", kind="maintenance",
            title="info-2", detail="d",
        )
        data = _build_event_data(project_root=tmp_path, adopted=False)
        result = generate(data)
        # PASS because no signal items — info shown in parens (B0 D6 mirror)
        assert "| Triage open | 0 open (2 info) | PASS |  |" in result

    def test_mixed_signal_and_info_renders_both_counts(self, tmp_path: Path):
        append_triage_item(
            tmp_path, source="phaseQuality", severity="high", kind="bug",
            title="signal", detail="d",
        )
        append_triage_item(
            tmp_path, source="drift", severity="info", kind="maintenance",
            title="noise", detail="d",
        )
        data = _build_event_data(project_root=tmp_path, adopted=False)
        result = generate(data)
        assert "| Triage open | 1 open (1 info) | WARN |" in result
        assert "1 actionable item" in result

    def test_dismissed_items_not_counted(self, tmp_path: Path):
        from triage import mark_status

        item_id = append_triage_item(
            tmp_path, source="phaseQuality", severity="high", kind="bug",
            title="t", detail="d",
        )
        mark_status(tmp_path, item_id, new_status="dismissed", by="test")
        data = _build_event_data(project_root=tmp_path, adopted=False)
        result = generate(data)
        assert "| Triage open | 0 open | PASS |  |" in result


class TestB1RegressionGuards:
    """Make sure existing indicators still render correctly under the new
    4-column layout."""

    def test_dependencies_row_still_present(self, tmp_path: Path):
        data = _build_event_data(project_root=tmp_path, adopted=False)
        data.dependencies = [
            DependencyInfo("react", "19.0.0", "runtime", "MIT"),
        ]
        result = generate(data)
        # 4-column row with explicit empty Why-warn cell
        assert "| Dependencies | 1 packages | INFO |  |" in result

    def test_copyleft_warn_carries_diagnostic(self, tmp_path: Path):
        data = _build_event_data(project_root=tmp_path, adopted=False)
        data.dependencies = [
            DependencyInfo("gpl-pkg", "1.0.0", "runtime", "GPL-3.0"),
        ]
        result = generate(data)
        assert "| Copyleft risk | 1 | WARN |" in result
        assert "1 copyleft license(s)" in result
        assert "sbom.md" in result


class TestB1ReviewFindingFixes:
    """Regression coverage for findings from the B.1 self-review pass."""

    def test_greenfield_no_build_events_review_row_has_diagnostic(
        self, tmp_path: Path,
    ):
        """Review H1: a greenfield project with only iterate events (no
        build events yet) used to render `All sections reviewed | 0/0 |
        WARN | |` — empty Why-warn cell, violates AC-5. Fix renders a
        pointer to /shipwright-build."""
        data = _build_event_data(project_root=tmp_path, adopted=False)
        # default _build_event_data gives one iterate event, zero build events
        result = generate(data)
        # WARN row with a non-empty diagnostic
        assert (
            "| All sections reviewed | 0/0 | WARN | "
            "no build events yet — run /shipwright-build first |"
        ) in result

    def test_malformed_severity_skipped_silently(self, tmp_path: Path):
        """Review M1 / ADR-055 D5: an item with severity outside the
        canonical enum is skipped from BOTH signal and info counts."""
        # Bypass append_triage_item's enum validation by hand-writing the
        # JSONL — simulates a corrupt-file scenario.
        triage_dir = tmp_path / ".shipwright"
        triage_dir.mkdir()
        (triage_dir / "triage.jsonl").write_text(
            json.dumps({"v": 1, "schema": "triage", "created": "2026-05-21T00:00:00Z"})
            + "\n"
            # malformed: severity is bogus
            + json.dumps({
                "event": "append", "id": "trg-deadbeef",
                "ts": "2026-05-21T01:00:00Z",
                "originalTs": "2026-05-21T01:00:00Z",
                "source": "test", "severity": "URGENT",
                "kind": "bug", "title": "t", "detail": "d",
                "status": "triage",
                "suggestedPriority": "P0", "suggestedDomain": "engineering",
            })
            + "\n",
            encoding="utf-8",
        )
        data = _build_event_data(project_root=tmp_path, adopted=False)
        result = generate(data)
        # Malformed item doesn't bump either counter
        assert "| Triage open | 0 open | PASS |  |" in result

    def test_signal_severity_whitelist_explicit(self, tmp_path: Path):
        """All four signal severities (critical/high/medium/low) contribute
        to the signal count."""
        for sev in ("critical", "high", "medium", "low"):
            append_triage_item(
                tmp_path, source="test", severity=sev, kind="bug",
                title=f"t-{sev}", detail="d",
            )
        data = _build_event_data(project_root=tmp_path, adopted=False)
        result = generate(data)
        assert "| Triage open | 4 open | WARN |" in result
