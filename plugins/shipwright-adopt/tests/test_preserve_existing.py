"""Unit tests for preserve_existing helper (sub-iterate C).

Trigger scenario this is built for: a real adoption run on a Windows +
multi-service repo overwrote a 16 KB load-bearing CLAUDE.md and a
137 KB decision_log.md (58 ADRs, 6 weeks of history) with thin scaffold
content and no backup. The user kept those files, lost everything else,
and discovered the destruction only after the fact.
"""

from __future__ import annotations

from pathlib import Path

from lib.preserve_existing import (
    BACKUPS_REL,
    count_adr_sections,
    is_loadbearing_claude_md,
    merge_decision_log,
    preserve_if_exists,
)


# preserve_if_exists
# ---------------------------------------------------------------------------

def test_preserve_if_exists_copies_to_backups(tmp_path: Path) -> None:
    target = tmp_path / "CLAUDE.md"
    target.write_text("original content X" * 100, encoding="utf-8")
    backup = preserve_if_exists(tmp_path, "CLAUDE.md")
    assert backup is not None
    assert backup.exists()
    assert backup.read_text(encoding="utf-8") == target.read_text(encoding="utf-8")
    # Original file untouched (this is a backup, not a move)
    assert target.exists()
    # Backup lands under .shipwright/adopt/backups/
    assert BACKUPS_REL in backup.as_posix()
    assert backup.name == "CLAUDE.md.preserved"


def test_preserve_if_exists_returns_none_when_absent(tmp_path: Path) -> None:
    backup = preserve_if_exists(tmp_path, "CLAUDE.md")
    assert backup is None


def test_preserve_if_exists_handles_nested_path(tmp_path: Path) -> None:
    nested = tmp_path / ".shipwright" / "agent_docs" / "decision_log.md"
    nested.parent.mkdir(parents=True)
    nested.write_text("# log", encoding="utf-8")
    backup = preserve_if_exists(tmp_path, ".shipwright/agent_docs/decision_log.md")
    assert backup is not None
    # Path inside backups should mirror the source layout
    assert backup.as_posix().endswith(".shipwright/agent_docs/decision_log.md.preserved")


def test_preserve_overwrites_stale_backup(tmp_path: Path) -> None:
    """Re-running adopt should refresh the backup, not stack timestamps."""
    target = tmp_path / "CLAUDE.md"
    target.write_text("v1", encoding="utf-8")
    preserve_if_exists(tmp_path, "CLAUDE.md")
    target.write_text("v2", encoding="utf-8")
    backup = preserve_if_exists(tmp_path, "CLAUDE.md")
    assert backup is not None
    assert backup.read_text(encoding="utf-8") == "v2"


# count_adr_sections
# ---------------------------------------------------------------------------

def test_count_adr_sections_counts_h2(tmp_path: Path) -> None:
    log = tmp_path / "decision_log.md"
    log.write_text(
        "# Decision Log\n\n"
        "## ADR-0001: First decision\n\nContext...\n\n"
        "## ADR-0002: Second decision\n\nContext...\n\n"
        "## ADR-0042: A later one\n\nContext...\n",
        encoding="utf-8",
    )
    assert count_adr_sections(log) == 3


def test_count_adr_sections_zero_for_empty(tmp_path: Path) -> None:
    log = tmp_path / "decision_log.md"
    log.write_text("# Decision Log\n\n_no ADRs yet_\n", encoding="utf-8")
    assert count_adr_sections(log) == 0


def test_count_adr_sections_zero_for_missing(tmp_path: Path) -> None:
    assert count_adr_sections(tmp_path / "missing.md") == 0


# is_loadbearing_claude_md
# ---------------------------------------------------------------------------

def test_is_loadbearing_claude_md_below_threshold(tmp_path: Path) -> None:
    p = tmp_path / "CLAUDE.md"
    p.write_text("tiny", encoding="utf-8")
    assert is_loadbearing_claude_md(p) is False


def test_is_loadbearing_claude_md_above_threshold(tmp_path: Path) -> None:
    p = tmp_path / "CLAUDE.md"
    p.write_text("x" * 2048, encoding="utf-8")
    assert is_loadbearing_claude_md(p) is True


def test_is_loadbearing_claude_md_missing(tmp_path: Path) -> None:
    assert is_loadbearing_claude_md(tmp_path / "missing.md") is False


# merge_decision_log
# ---------------------------------------------------------------------------

def test_merge_decision_log_preserves_existing_adrs(tmp_path: Path) -> None:
    """Existing ADRs must survive verbatim — that's the whole point."""
    new_log_content = (
        "# Decision Log — adopted\n\n"
        "## ADR-0001: Adopt this repository\n\n"
        "- Status: accepted\n\nNew adoption decision.\n\n---\n"
    )
    existing = tmp_path / "decision_log.md"
    existing_body = (
        "# Decision Log — original\n\n"
        "## ADR-0001: Use Postgres\n\nDecided 2026-01-01.\n\n---\n\n"
        "## ADR-0042: Migrate to NATS\n\nDecided 2026-04-01.\n\n---\n"
    )
    existing.write_text(existing_body, encoding="utf-8")
    merged, info = merge_decision_log(new_log_content, existing)
    # Existing ADR titles must appear in the merged output
    assert "Use Postgres" in merged
    assert "Migrate to NATS" in merged
    assert "Decided 2026-04-01" in merged
    # New adoption ADR should also appear
    assert "Adopt this repository" in merged
    # Info has counts
    assert info["existing_adrs"] == 2
    assert info["action"] == "merged"


def test_merge_decision_log_no_merge_when_existing_has_no_adrs(tmp_path: Path) -> None:
    """Empty existing log → use new content as-is."""
    new_log_content = "# new\n\n## ADR-0001: x\n"
    existing = tmp_path / "decision_log.md"
    existing.write_text("# Decision Log\n\nempty\n", encoding="utf-8")
    merged, info = merge_decision_log(new_log_content, existing)
    assert merged == new_log_content
    assert info["existing_adrs"] == 0
    assert info["action"] == "overwritten"
