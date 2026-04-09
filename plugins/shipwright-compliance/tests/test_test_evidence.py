"""Tests for test_evidence.py."""

from __future__ import annotations

from pathlib import Path

from scripts.lib.data_collector import ComplianceData, RequirementInfo, WorkEvent, collect_all
from scripts.lib.test_evidence import generate, generate_file


class TestGenerate:
    def test_produces_markdown(self, project_root: Path):
        data = collect_all(project_root)
        result = generate(data)
        assert "# Test Evidence Report" in result
        assert "## Summary" in result

    def test_summary_metrics(self, project_root: Path):
        data = collect_all(project_root)
        result = generate(data)
        assert "| Total sections tested | 3 |" in result
        assert "| Unit tests passed | 16 |" in result
        assert "| Unit tests failed | 0 |" in result

    def test_per_split_results(self, project_root: Path):
        data = collect_all(project_root)
        result = generate(data)
        assert "## Per-Split Results" in result
        assert "01-login" in result or "01-auth" in result  # Split or section name
        assert "| Unit |" in result  # Layer breakdown present

    def test_code_review_evidence(self, project_root: Path):
        data = collect_all(project_root)
        result = generate(data)
        assert "## Code Review Evidence" in result
        assert "PASS" in result

    def test_mermaid_pyramid(self, project_root: Path):
        data = collect_all(project_root)
        result = generate(data)
        assert "```mermaid" in result
        assert "Unit Tests" in result

    def test_empty_data(self, empty_project_root: Path):
        data = collect_all(empty_project_root)
        result = generate(data)
        assert "| Total sections tested | 0 |" in result


class TestProgressionOrder:
    def test_newest_event_first(self, empty_project_root: Path):
        """Row 1 in Test Progression table is the newest event."""
        data = ComplianceData(project_root=empty_project_root, timestamp="2026-04-06T00:00:00Z")
        data.work_events = [
            WorkEvent(
                id="ev-old", timestamp="2026-04-01T10:00:00Z", source="build",
                section="01-auth", tests_passed=10, tests_total=10,
            ),
            WorkEvent(
                id="ev-new", timestamp="2026-04-05T10:00:00Z", source="iterate",
                description="Add login flow", tests_passed=15, tests_total=15,
            ),
        ]
        result = generate(data)
        lines = result.splitlines()
        # Find data rows in Test Progression table (skip header/separator)
        table_rows = [
            l for l in lines
            if l.startswith("| ") and ("build" in l or "iterate" in l)
        ]
        assert len(table_rows) >= 2
        assert "iterate" in table_rows[0], "Newest event (iterate) should be first row"
        assert "build" in table_rows[1], "Older event (build) should be second row"


def _make_data(tmp_path, *, baseline=0, tests_passed=830, tests_total=831):
    """Helper to build ComplianceData with one work event for baseline tests."""
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


class TestBaselineFailures:
    def test_baseline_failures_give_pass_baseline(self, tmp_path: Path):
        """Events with failures <= baseline get PASS (baseline) not FAIL."""
        data = _make_data(tmp_path, baseline=1, tests_passed=830, tests_total=831)
        result = generate(data)
        assert "PASS (baseline)" in result
        assert "| FAIL |" not in result

    def test_failures_beyond_baseline_still_fail(self, tmp_path: Path):
        """Events with failures > baseline still get FAIL."""
        data = _make_data(tmp_path, baseline=1, tests_passed=828, tests_total=831)
        result = generate(data)
        assert "FAIL" in result
        assert "PASS (baseline)" not in result

    def test_no_baseline_unchanged(self, tmp_path: Path):
        """Without baseline, behavior is strict equality."""
        data = _make_data(tmp_path, baseline=0, tests_passed=830, tests_total=831)
        result = generate(data)
        assert "FAIL" in result
        assert "PASS (baseline)" not in result

    def test_all_passing_ignores_baseline(self, tmp_path: Path):
        """When all tests pass, result is PASS regardless of baseline."""
        data = _make_data(tmp_path, baseline=1, tests_passed=831, tests_total=831)
        result = generate(data)
        assert "| PASS |" in result
        assert "baseline" not in result


class TestGenerateFile:
    def test_writes_file(self, project_root: Path):
        data = collect_all(project_root)
        path = generate_file(project_root, data)
        assert path.exists()
        assert path.name == "test-evidence.md"
