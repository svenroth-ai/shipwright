"""Tests for sbom_generator.py."""

from __future__ import annotations

from pathlib import Path

from scripts.lib.data_collector import ComplianceData, DependencyInfo, collect_all
from scripts.lib.sbom_generator import generate, generate_file


def _make_data(deps: list[DependencyInfo]) -> ComplianceData:
    data = ComplianceData(project_root=Path("."))
    data.dependencies = deps
    data.timestamp = "2026-03-21T14:00:00Z"
    return data


class TestGenerate:
    def test_produces_markdown(self, project_root: Path):
        data = collect_all(project_root)
        result = generate(data)
        assert "# Software Bill of Materials (SBOM)" in result
        assert "## Summary" in result

    def test_summary_counts(self, project_root: Path):
        data = collect_all(project_root)
        result = generate(data)
        assert "| Runtime dependencies | 8 |" in result
        assert "| Dev dependencies | 5 |" in result
        assert "| Total packages | 13 |" in result

    def test_runtime_table(self, project_root: Path):
        data = collect_all(project_root)
        result = generate(data)
        assert "## Runtime Dependencies" in result
        assert "next" in result
        assert "react" in result

    def test_dev_table(self, project_root: Path):
        data = collect_all(project_root)
        result = generate(data)
        assert "## Dev Dependencies" in result
        assert "vitest" in result
        assert "typescript" in result

    def test_mermaid_pie(self, project_root: Path):
        data = collect_all(project_root)
        result = generate(data)
        assert "```mermaid" in result
        assert "pie title" in result

    def test_copyleft_warning(self):
        deps = [
            DependencyInfo("react", "19.0.0", "runtime", "MIT"),
            DependencyInfo("gpl-pkg", "1.0.0", "runtime", "GPL-3.0"),
        ]
        result = generate(_make_data(deps))
        assert "WARNING: Copyleft licenses detected" in result
        assert "gpl-pkg" in result

    def test_no_copyleft(self):
        deps = [
            DependencyInfo("react", "19.0.0", "runtime", "MIT"),
        ]
        result = generate(_make_data(deps))
        assert "No copyleft licenses detected" in result

    def test_unknown_licenses_section(self, project_root: Path):
        data = collect_all(project_root)
        result = generate(data)
        # All licenses are unknown because no node_modules
        assert "## Unknown Licenses" in result
        assert "13 packages" in result

    def test_no_deps(self, empty_project_root: Path):
        data = collect_all(empty_project_root)
        result = generate(data)
        assert "No dependency manifests found" in result


class TestGenerateFile:
    def test_writes_file(self, project_root: Path):
        data = collect_all(project_root)
        path = generate_file(project_root, data)
        assert path.exists()
        assert path.name == "sbom.md"
