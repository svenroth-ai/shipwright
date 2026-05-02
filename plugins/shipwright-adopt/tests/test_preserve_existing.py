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
    parse_max_adr_id,
    preserve_if_exists,
)


_BROWNFIELD_LOG_WITH_GAP = (
    "# Decision Log — original\n\n"
    "## ADR-001: Use Postgres\n\nDecided 2026-01-01.\n\n---\n\n"
    "## ADR-002: Adopt monorepo\n\nDecided 2026-01-05.\n\n---\n\n"
    "## ADR-027: Switch to NATS\n\nDecided 2026-02-10.\n\n---\n\n"
    "## ADR-045: Pivot to assistant-ui\n\nDecided 2026-03-01.\n\n---\n\n"
    "## ADR-045b: Pivot follow-up details\n\nDisambig suffix.\n\n---\n\n"
    "## ADR-053: ADR-053: Stylistic title duplication\n\n"
    "Decided 2026-03-20.\n\n---\n\n"
    "### ADR-058: Compact H3 entry\n\nDecided 2026-04-01.\n"
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


# parse_max_adr_id
# ---------------------------------------------------------------------------

def test_parse_max_adr_id_finds_highest_3plus_digit_id() -> None:
    """Robust against H3, disambiguation suffixes, and title duplication."""
    assert parse_max_adr_id(_BROWNFIELD_LOG_WITH_GAP) == 58


def test_parse_max_adr_id_returns_zero_for_empty_content() -> None:
    assert parse_max_adr_id("# Decision Log\n\n_no ADRs_\n") == 0


def test_parse_max_adr_id_ignores_under_3_digit_historical_ids() -> None:
    """1- and 2-digit ids predate Shipwright's canon — adopt won't
    inherit them as the next-free-id source."""
    body = (
        "# Decision Log\n\n"
        "## ADR-1: Ancient one-digit\n\n---\n\n"
        "## ADR-12: Older two-digit\n\n---\n\n"
    )
    assert parse_max_adr_id(body) == 0


def test_parse_max_adr_id_handles_h3_compact_format() -> None:
    body = (
        "# Decision Log\n\n"
        "### ADR-007: Sentry for errors\n\n---\n\n"
        "### ADR-099: A later one\n\n---\n\n"
    )
    assert parse_max_adr_id(body) == 99


def test_parse_max_adr_id_handles_disambiguation_suffix() -> None:
    """ADR-045b should be recognised as numeric id 45 (suffix dropped)."""
    body = (
        "# Decision Log\n\n"
        "## ADR-045: Original\n\n---\n\n"
        "## ADR-045b: Disambig\n\n---\n\n"
    )
    assert parse_max_adr_id(body) == 45


def test_parse_max_adr_id_handles_duplicated_title_form() -> None:
    """The webui-style "### ADR-053: ADR-053: Foo" must still match."""
    body = "### ADR-053: ADR-053: Stylistic title duplication\n\n"
    assert parse_max_adr_id(body) == 53


# Brownfield-with-gap regression fixture (from the bug report)
# ---------------------------------------------------------------------------

def test_merge_decision_log_reports_max_existing_in_info(tmp_path: Path) -> None:
    """merge_decision_log returns the parsed max id so callers can
    pick the next free ADR number without re-scanning the file."""
    new_log_content = (
        "# Decision Log — adopted\n\n"
        "## ADR-059: Adopt this repository\n\nNew adoption.\n"
    )
    existing = tmp_path / "decision_log.md"
    existing.write_text(_BROWNFIELD_LOG_WITH_GAP, encoding="utf-8")
    merged, info = merge_decision_log(
        new_log_content, existing, adoption_adr_id=59,
    )
    assert info["max_existing_adr_id"] == 58
    assert info["existing_adrs"] >= 5  # 7 sections in the fixture
    # Dynamic preamble carries the actual range, not a hardcoded number
    assert "ADR-058" in merged
    assert "Adoption ADR: ADR-059." in merged
    # Existing ADRs still survive verbatim
    assert "ADR-045b: Pivot follow-up" in merged
    assert "ADR-053: ADR-053: Stylistic title duplication" in merged
