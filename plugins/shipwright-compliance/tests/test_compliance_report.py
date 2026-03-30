"""Tests for compliance_report.py (dashboard)."""

from __future__ import annotations

from pathlib import Path

from scripts.lib.data_collector import ComplianceData, DependencyInfo, collect_all
from scripts.lib.compliance_report import generate, generate_file


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
        assert "| Tests passing | 16/16 | PASS |" in result
        assert "| Copyleft licenses | 0 | PASS |" in result

    def test_compliance_artifacts_links(self, project_root: Path):
        data = collect_all(project_root)
        result = generate(data)
        assert "traceability-matrix.md" in result
        assert "test-evidence.md" in result
        assert "change-history.md" in result
        assert "sbom.md" in result

    def test_traceability_overview(self, project_root: Path):
        data = collect_all(project_root)
        result = generate(data)
        assert "## Traceability Overview" in result

    def test_cost_summary(self, project_root: Path):
        data = collect_all(project_root)
        result = generate(data)
        assert "## Cost Summary" in result
        assert "| Total estimated tokens | 105,000 |" in result
        assert "| Total estimated API calls | 30 |" in result

    def test_copyleft_detection(self):
        data = ComplianceData(project_root=Path("."))
        data.timestamp = "2026-03-21T14:00:00Z"
        data.configs = {"run": {"profile": "test", "scope": "full_app"}}
        data.dependencies = [
            DependencyInfo("react", "19.0.0", "runtime", "MIT"),
            DependencyInfo("gpl-pkg", "1.0.0", "runtime", "GPL-3.0"),
        ]
        result = generate(data)
        assert "| Copyleft licenses | 1 | WARN |" in result

    def test_empty_data(self, empty_project_root: Path):
        data = collect_all(empty_project_root)
        result = generate(data)
        assert "# Compliance Dashboard" in result
        assert "| Sections completed | 0/0 | WARN |" in result


class TestGenerateFile:
    def test_writes_file(self, project_root: Path):
        data = collect_all(project_root)
        path = generate_file(project_root, data)
        assert path.exists()
        assert path.name == "dashboard.md"
        content = path.read_text(encoding="utf-8")
        assert "# Compliance Dashboard" in content
