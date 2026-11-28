"""Tests for change_history.py."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from scripts.lib.collectors.change_history import collect_git_history
from scripts.lib.data_collector import CommitEntry, ComplianceData
from scripts.lib.change_history import generate, generate_file

sys.path.insert(0, str(Path(__file__).parent))
from rtm_hook_test_support import hook_env, scrub_git_env  # noqa: E402, F401 - scrub_git_env is autouse


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
            CommitEntry("def", "fix", None, "fix bug", "2026-03-21", "Ada"),
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


@pytest.mark.covers("FR-01.10/AC01")
class TestCoAuthorAttribution:
    """Root cause: AI attribution read the author name only, never trailers."""

    def test_co_author_trailer_counts_as_ai(self):
        commits = [
            CommitEntry("a", "feat", None, "x", "2026-03-20", "Human",
                        co_authors=("Claude Opus <noreply@anthropic.com>",)),
            CommitEntry("b", "fix", None, "y", "2026-03-20", "Human"),
        ]
        result = generate(_make_data(commits))
        assert "| AI-assisted commits | 1 |" in result
        assert "| Human-authored commits | 1 |" in result

    def test_unrelated_co_author_is_human(self):
        c = CommitEntry("a", "feat", None, "x", "d", "Human", co_authors=("Ada <a@b.c>",))
        assert not c.is_ai_assisted


@pytest.mark.covers("FR-01.10/AC01")
class TestCollectGitHistoryTrailers:
    def _repo(self, tmp_path: Path) -> Path:
        def git(*a):
            subprocess.run(["git", *a], cwd=tmp_path, check=True, capture_output=True, env=hook_env(tmp_path))
        git("init", "-q")
        git("config", "user.name", "Human")
        git("config", "user.email", "h@example.com")
        git("config", "commit.gpgsign", "false")
        for i, trailer in enumerate([
            "Co-Authored-By: Claude <noreply@anthropic.com>",
            "Co-authored-by: Claude Opus <noreply@anthropic.com>",
            "",
            "Co-authored-by: Ada <a@b.c>\nCo-Authored-By: Claude <noreply@anthropic.com>",
        ]):
            msg = f"feat: change {i} with | pipe"
            if trailer:
                msg += f"\n\n{trailer}"
            git("commit", "-q", "--allow-empty", "-m", msg)
        return tmp_path

    def test_trailers_read_case_insensitively(self, tmp_path: Path):
        commits = collect_git_history(self._repo(tmp_path))
        assert len(commits) == 4
        by_desc = {c.description: c for c in commits}
        assert [by_desc[f"change {i} with | pipe"].is_ai_assisted for i in range(4)] == [
            True, True, False, True]
        assert len(by_desc["change 3 with | pipe"].co_authors) == 2

    def test_email_alone_does_not_count(self):
        c = CommitEntry("a", "feat", None, "x", "d", "Human", co_authors=("Ada <ada@claude.example>",))
        assert not c.is_ai_assisted
