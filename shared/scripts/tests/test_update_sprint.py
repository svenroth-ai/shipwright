"""Tests for update_sprint.py."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.update_sprint import update_sprint_table

SAMPLE_SPRINT = """\
# Current Sprint

## Sections

| # | Section | Status | Commit |
|---|---------|--------|--------|
| 01 | project-setup | not_started | — |
| 02 | database-schema | not_started | — |
| 03 | authentication | not_started | — |
"""


class TestUpdateSprintTable:
    def test_updates_matching_section(self):
        result = update_sprint_table(SAMPLE_SPRINT, "01-project-setup", "complete", "abc1234")
        assert "| 01 | project-setup | complete | abc1234 |" in result

    def test_leaves_other_sections_unchanged(self):
        result = update_sprint_table(SAMPLE_SPRINT, "01-project-setup", "complete", "abc1234")
        assert "| 02 | database-schema | not_started | — |" in result
        assert "| 03 | authentication | not_started | — |" in result

    def test_matches_without_numeric_prefix(self):
        result = update_sprint_table(SAMPLE_SPRINT, "02-database-schema", "in_progress", "")
        assert "| 02 | database-schema | in_progress |" in result

    def test_no_match_returns_unchanged(self):
        result = update_sprint_table(SAMPLE_SPRINT, "99-nonexistent", "complete", "abc")
        assert result == SAMPLE_SPRINT

    def test_updates_commit_field(self):
        result = update_sprint_table(SAMPLE_SPRINT, "03-authentication", "complete", "def5678")
        assert "def5678" in result

    def test_empty_commit_shows_dash(self):
        result = update_sprint_table(SAMPLE_SPRINT, "01-project-setup", "in_progress", "")
        assert "| 01 | project-setup | in_progress | — |" in result
