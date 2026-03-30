"""Tests for change_history.py."""

from __future__ import annotations

from pathlib import Path

from scripts.lib.data_collector import CommitEntry, ComplianceData
from scripts.lib.change_history import generate, generate_file


def _make_data(commits: list[CommitEntry]) -> ComplianceData:
    """Create minimal ComplianceData with commits."""
    data = ComplianceData(project_root=Path("."))
    data.commits = commits
    data.timestamp = "2026-03-21T14:00:00Z"
    return data


class TestGenerate:
    def test_produces_markdown(self):
        commits = [
            CommitEntry("abc123", "feat", "auth", "add login", "2026-03-20T10:00:00+00:00", "Claude"),
            CommitEntry("def456", "fix", "auth", "fix timeout", "2026-03-21T10:00:00+00:00", "Claude"),
        ]
        result = generate(_make_data(commits))
        assert "# Commit Change Log" in result
        assert "Total commits: 2" in result

    def test_groups_by_type(self):
        commits = [
            CommitEntry("abc", "feat", "auth", "add login", "2026-03-20", "Claude"),
            CommitEntry("def", "feat", "api", "add endpoint", "2026-03-20", "Claude"),
            CommitEntry("ghi", "fix", "auth", "fix timeout", "2026-03-21", "Claude"),
        ]
        result = generate(_make_data(commits))
        assert "### Features (feat) — 2 commits" in result
        assert "### Fixes (fix) — 1 commits" in result

    def test_mermaid_pie(self):
        commits = [
            CommitEntry("abc", "feat", None, "something", "2026-03-20", "Claude"),
        ]
        result = generate(_make_data(commits))
        assert "```mermaid" in result
        assert "pie title" in result

    def test_ai_attribution(self):
        commits = [
            CommitEntry("abc", "feat", None, "add feature", "2026-03-20", "Claude"),
            CommitEntry("def", "fix", None, "fix bug", "2026-03-21", "Sven"),
        ]
        result = generate(_make_data(commits))
        assert "| AI-assisted commits | 1 |" in result
        assert "| Human-authored commits | 1 |" in result

    def test_no_commits(self):
        result = generate(_make_data([]))
        assert "No commits found" in result

    def test_commit_table(self):
        commits = [
            CommitEntry("abc123", "feat", "auth", "add magic link", "2026-03-20T10:00:00+00:00", "Claude"),
        ]
        result = generate(_make_data(commits))
        assert "| 2026-03-20 | auth | add magic link | abc123 |" in result


class TestGenerateFile:
    def test_writes_file(self, project_root: Path):
        data = ComplianceData(project_root=project_root)
        data.commits = [
            CommitEntry("abc", "feat", None, "test", "2026-03-20", "Claude"),
        ]
        data.timestamp = "2026-03-21T14:00:00Z"
        path = generate_file(project_root, data)
        assert path.exists()
        assert path.name == "change-history.md"
