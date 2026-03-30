"""Tests for rtm_generator.py."""

from __future__ import annotations

from pathlib import Path

from scripts.lib.data_collector import ComplianceData, SectionInfo, SplitInfo, collect_all
from scripts.lib.rtm_generator import generate, generate_file


class TestGenerate:
    def test_produces_markdown(self, project_root: Path):
        data = collect_all(project_root)
        result = generate(data)
        assert "# Requirements Traceability Matrix" in result
        assert "## Matrix" in result
        assert "## Summary" in result

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

    def test_pass_status_for_complete_sections(self, project_root: Path):
        data = collect_all(project_root)
        result = generate(data)
        assert "PASS" in result

    def test_findings_formatted(self, project_root: Path):
        data = collect_all(project_root)
        result = generate(data)
        # 03-profile has 2 findings (1 fixed, 1 deferred)
        assert "1 fixed" in result
        assert "1 deferred" in result


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
        assert (root / "compliance").exists()
        assert path.exists()
