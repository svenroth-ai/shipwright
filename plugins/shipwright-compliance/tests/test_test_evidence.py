"""Tests for test_evidence.py."""

from __future__ import annotations

from pathlib import Path

from scripts.lib.data_collector import ComplianceData, collect_all
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


class TestGenerateFile:
    def test_writes_file(self, project_root: Path):
        data = collect_all(project_root)
        path = generate_file(project_root, data)
        assert path.exists()
        assert path.name == "test-evidence.md"
