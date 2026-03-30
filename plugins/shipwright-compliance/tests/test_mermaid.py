"""Tests for mermaid.py diagram builders."""

from __future__ import annotations

from scripts.lib.data_collector import CommitEntry, DependencyInfo, SectionInfo
from scripts.lib.mermaid import (
    commit_type_pie,
    license_pie,
    pipeline_status_diagram,
    testing_pyramid_diagram,
)


class TestPipelineStatusDiagram:
    def test_complete_pipeline(self):
        configs = {
            "run": {"status": "complete", "current_step": "changelog"},
            "project": {"status": "complete"},
            "plan": {"status": "complete"},
            "build": {"status": "complete"},
        }
        result = pipeline_status_diagram(configs)
        assert "```mermaid" in result
        assert "flowchart LR" in result
        assert "COMPLETE" in result
        assert "#4CAF50" in result  # green

    def test_in_progress_pipeline(self):
        configs = {
            "run": {"status": "in_progress", "current_step": "build"},
            "project": {"status": "complete"},
            "plan": {"status": "complete"},
            "build": {},
        }
        result = pipeline_status_diagram(configs)
        assert "IN PROGRESS" in result
        assert "#FFC107" in result  # yellow
        assert "#9E9E9E" in result  # gray for pending phases

    def test_empty_configs(self):
        configs = {}
        result = pipeline_status_diagram(configs)
        assert "```mermaid" in result
        assert "PENDING" in result


class TestCommitTypePie:
    def test_with_commits(self):
        commits = [
            CommitEntry("abc", "feat", "auth", "add login", "2026-03-20", "Claude"),
            CommitEntry("def", "feat", "api", "add endpoint", "2026-03-20", "Claude"),
            CommitEntry("ghi", "fix", "auth", "fix timeout", "2026-03-21", "Claude"),
            CommitEntry("jkl", "test", "auth", "add tests", "2026-03-21", "Claude"),
        ]
        result = commit_type_pie(commits)
        assert "```mermaid" in result
        assert "pie title" in result
        assert '"feat" : 2' in result
        assert '"fix" : 1' in result
        assert '"test" : 1' in result

    def test_empty_commits(self):
        result = commit_type_pie([])
        assert "no commits" in result


class TestLicensePie:
    def test_with_dependencies(self):
        deps = [
            DependencyInfo("react", "19.2.0", "runtime", "MIT"),
            DependencyInfo("next", "16.2.0", "runtime", "MIT"),
            DependencyInfo("playwright", "1.50.0", "dev", "Apache-2.0"),
        ]
        result = license_pie(deps)
        assert "```mermaid" in result
        assert '"MIT" : 2' in result
        assert '"Apache-2.0" : 1' in result

    def test_empty_dependencies(self):
        result = license_pie([])
        assert "no packages" in result


class TestTestPyramidDiagram:
    def test_with_sections(self):
        sections = [
            SectionInfo("01-login", "01-auth", "complete", "abc", 5, 5, 1, 1, 0, 0),
            SectionInfo("02-rbac", "01-auth", "complete", "def", 8, 8, 0, 0, 0, 0),
        ]
        result = testing_pyramid_diagram(sections)
        assert "```mermaid" in result
        assert "13/13 passed" in result
        assert "2 sections reviewed" in result
