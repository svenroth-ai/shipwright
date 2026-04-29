"""Tests for rtm_generator.py."""

from __future__ import annotations

from pathlib import Path

from scripts.lib.data_collector import (
    ComplianceData, KnownFailure, RequirementInfo, SectionInfo, SplitInfo, WorkEvent, collect_all,
)
from scripts.lib.rtm_generator import generate, generate_file


class TestGenerate:
    def test_produces_markdown(self, project_root: Path):
        data = collect_all(project_root)
        result = generate(data)
        assert "# Requirements Traceability Matrix" in result
        assert "## Section Traceability" in result
        assert "## Coverage Summary" in result

    def test_contains_section_data(self, project_root: Path):
        data = collect_all(project_root)
        result = generate(data)
        assert "01-login" in result
        assert "02-rbac" in result
        assert "03-profile" in result
        assert "abc123def456" in result  # commit hash

    def test_no_traceability_flow_diagram(self, project_root: Path):
        data = collect_all(project_root)
        result = generate(data)
        assert "## Traceability Flow" not in result
        assert "flowchart TD" not in result

    def test_summary_metrics(self, project_root: Path):
        data = collect_all(project_root)
        result = generate(data)
        assert "| Total splits | 3 |" in result
        assert "| Total sections | 3 |" in result
        assert "| Traceability coverage | 100% |" in result

    def test_empty_data(self, empty_project_root: Path):
        data = collect_all(empty_project_root)
        result = generate(data)
        assert "No sections available yet" in result

    def test_section_pass_status(self, project_root: Path):
        data = collect_all(project_root)
        result = generate(data)
        # Section traceability shows PASS for sections with green unit tests
        assert "PASS" in result

    def test_findings_in_summary(self, project_root: Path):
        data = collect_all(project_root)
        result = generate(data)
        # 03-profile has 2 findings (1 fixed, 1 deferred) -> totals in summary
        assert "| Total review findings | 3 |" in result
        assert "| Unresolved findings | 1 |" in result


def _make_data(tmp_path, *, baseline=0, tests_passed=830, tests_total=831):
    """Helper to build ComplianceData with one FR and one work event."""
    data = ComplianceData(project_root=tmp_path, timestamp="2026-04-06T00:00:00Z")
    data.baseline_failure_count = baseline
    we = WorkEvent(
        id="ev-1", timestamp="2026-04-06T10:00:00Z", source="iterate",
        description="Add feature", tests_passed=tests_passed, tests_total=tests_total,
        affected_frs=["FR-01.01"],
    )
    data.work_events = [we]
    data.requirements = [
        RequirementInfo(id="FR-01.01", text="Login works", priority="Must", split="01-auth"),
    ]
    return data


class TestKnownFailures:
    def test_baseline_failures_give_covered_baseline(self, tmp_path: Path):
        """FRs with failures <= baseline get COVERED (baseline) not FAIL."""
        data = _make_data(tmp_path, baseline=1, tests_passed=830, tests_total=831)
        result = generate(data)
        assert "COVERED (baseline)" in result
        assert "| FAIL |" not in result

    def test_failures_beyond_baseline_still_fail(self, tmp_path: Path):
        """FRs with failures > baseline still get FAIL."""
        data = _make_data(tmp_path, baseline=1, tests_passed=828, tests_total=831)
        result = generate(data)
        assert "FAIL" in result
        assert "COVERED (baseline)" not in result

    def test_no_known_failures_unchanged(self, tmp_path: Path):
        """Without known_failures, behavior is identical to current."""
        data = _make_data(tmp_path, baseline=0, tests_passed=830, tests_total=831)
        result = generate(data)
        assert "FAIL" in result
        assert "COVERED (baseline)" not in result

    def test_all_passing_ignores_baseline(self, tmp_path: Path):
        """When all tests pass, status is COVERED regardless of baseline."""
        data = _make_data(tmp_path, baseline=1, tests_passed=831, tests_total=831)
        result = generate(data)
        assert "COVERED" in result
        assert "baseline" not in result


class TestGenerateFile:
    def test_writes_file(self, project_root: Path):
        data = collect_all(project_root)
        path = generate_file(project_root, data)
        assert path.exists()
        assert path.name == "traceability-matrix.md"
        content = path.read_text(encoding="utf-8")
        assert "# Requirements Traceability Matrix" in content

    def test_creates_compliance_dir(self, tmp_path: Path):
        """If compliance/ doesn't exist, generate_file creates it."""
        root = tmp_path / "project"
        root.mkdir()
        data = ComplianceData(project_root=root)
        data.timestamp = "2026-03-21T14:00:00Z"
        path = generate_file(root, data)
        assert (root / ".shipwright" / "compliance").exists()
        assert path.exists()
