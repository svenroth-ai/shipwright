"""Tests for changelog module."""

import pytest
from changelog_corpus import ENTRY, FILE_SHAPES, significant_lines

from lib.changelog import (
    categorize_commits,
    generate_entry,
    update_changelog,
)


def test_categorize_commits():
    parsed = [
        {"type": "feat", "scope": "auth", "description": "add login", "breaking": False},
        {"type": "fix", "scope": "api", "description": "handle null", "breaking": False},
        {"type": "refactor", "scope": None, "description": "clean up", "breaking": False},
        {"type": "docs", "scope": None, "description": "update README", "breaking": False},
    ]
    sections = categorize_commits(parsed)

    assert "Added" in sections
    assert "Fixed" in sections
    assert "Changed" in sections
    assert "Documentation" in sections
    assert len(sections["Added"]) == 1
    assert "feat(auth): add login" in sections["Added"][0]


def test_categorize_breaking():
    parsed = [
        {"type": "feat", "scope": None, "description": "redesign", "breaking": True},
    ]
    sections = categorize_commits(parsed)
    assert "Breaking Changes" in sections
    assert "Added" in sections  # Also in Added


def test_generate_entry():
    sections = {
        "Added": ["feat(auth): add login"],
        "Fixed": ["fix(api): handle null"],
    }
    entry = generate_entry("1.0.0", sections, "2026-03-21")

    assert "## [1.0.0] - 2026-03-21" in entry
    assert "### Added" in entry
    assert "### Fixed" in entry
    assert "feat(auth): add login" in entry


def test_generate_entry_empty_sections():
    sections = {"Added": ["feat: something"]}
    entry = generate_entry("0.1.0", sections, "2026-03-21")

    assert "### Added" in entry
    assert "### Fixed" not in entry  # Empty section omitted


def test_update_changelog_new_file(tmp_path):
    changelog = tmp_path / "CHANGELOG.md"
    entry = "## [0.1.0] - 2026-03-21\n\n### Added\n- feat: first feature\n"

    content = update_changelog(changelog, entry)

    assert changelog.exists()
    assert "# Changelog" in content
    assert "[Unreleased]" in content
    assert "[0.1.0]" in content


def test_update_changelog_existing(tmp_path):
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(
        "# Changelog\n\n## [Unreleased]\n\n## [0.1.0] - 2026-03-15\n\n### Added\n- first\n"
    )

    entry = "## [0.2.0] - 2026-03-21\n\n### Added\n- feat: second feature\n"
    content = update_changelog(changelog, entry)

    # New entry should be between Unreleased and 0.1.0
    unreleased_pos = content.index("[Unreleased]")
    new_entry_pos = content.index("[0.2.0]")
    old_entry_pos = content.index("[0.1.0]")

    assert unreleased_pos < new_entry_pos < old_entry_pos


# --- Data preservation (trg-6690d175) -------------------------------------


def test_update_changelog_preserves_file_without_unreleased_marker(tmp_path):
    """AC1: a history file with no [Unreleased] marker must survive intact.

    This is the reported critical defect: the writer rebuilt the file from a
    fresh header and dropped everything it had just read.
    """
    changelog = tmp_path / "CHANGELOG.md"
    original = FILE_SHAPES[0]
    changelog.write_text(original, encoding="utf-8")

    content = update_changelog(changelog, ENTRY)

    for line in significant_lines(original):
        assert line in content, f"lost line: {line!r}"
    assert content.startswith("# Release History")
    # New section goes above the most recent released one.
    assert content.index("## [1.1.0]") < content.index("## [1.0.0]")


def test_update_changelog_preserves_pending_unreleased_bullets(tmp_path):
    """AC2: pending [Unreleased] bullets survive when no released section exists."""
    changelog = tmp_path / "CHANGELOG.md"
    original = FILE_SHAPES[1]
    changelog.write_text(original, encoding="utf-8")

    content = update_changelog(changelog, ENTRY)

    assert "- feat: pending one" in content
    assert "- fix: pending two" in content
    assert content.index("- fix: pending two") < content.index("## [1.1.0]")


def test_update_changelog_replacement_stops_at_whitespace_variant_heading(tmp_path):
    """A tab-separated heading still ends a section being replaced.

    `SECTION_HEADING_RE` accepts any whitespace after `##`, so the boundary
    predicate must too. When it did not, replacing 1.1.0 ran straight through
    the tab-headed 1.0.0 below it and deleted that release.
    """
    changelog = tmp_path / "CHANGELOG.md"
    original = (
        "# Changelog\n\n"
        "## [1.1.0] - 2026-07-27\n\n### Fixed\n- fix: original wording\n\n"
        "##\t[1.0.0] - 2024-01-10\n\n### Added\n- first stable release\n"
    )
    changelog.write_text(original, encoding="utf-8")

    content = update_changelog(
        changelog, "## [1.1.0] - 2026-07-27\n\n### Fixed\n- fix: revised wording\n"
    )

    assert "##\t[1.0.0] - 2024-01-10" in content
    assert "- first stable release" in content
    assert "- fix: revised wording" in content
    assert "- fix: original wording" not in content
    assert content.count("## [1.1.0]") == 1


# --- Idempotent re-run (trg-6690d175, second item) -------------------------


def test_update_changelog_is_idempotent_on_rerun(tmp_path):
    """AC5: an interrupted run re-executed must not duplicate the version."""
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(FILE_SHAPES[2], encoding="utf-8")

    first = update_changelog(changelog, ENTRY)
    second = update_changelog(changelog, ENTRY)

    assert second == first
    assert second.count("## [1.1.0]") == 1


def test_update_changelog_replaces_same_version_section(tmp_path):
    """AC6: re-running with a revised entry replaces that version's section."""
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(FILE_SHAPES[2], encoding="utf-8")

    update_changelog(changelog, "## [1.1.0] - 2026-07-27\n\n### Fixed\n- fix: original wording\n")
    content = update_changelog(
        changelog,
        "## [1.1.0] - 2026-07-27\n\n### Added\n- feat: extra\n\n### Fixed\n- fix: revised wording\n",
    )

    assert content.count("## [1.1.0]") == 1
    assert "- fix: revised wording" in content
    assert "- fix: original wording" not in content
    assert "- feat: extra" in content
    # Neighbours untouched.
    assert "## [Unreleased]" in content
    assert "## [1.0.0] - 2024-01-10" in content
    assert "- first" in content


# --- Refuse rather than guess ---------------------------------------------


@pytest.mark.parametrize(
    "bad_entry",
    [
        "### Added\n- feat: no version heading at all\n",
        "## [Unreleased]\n\n- feat: not a released section\n",
    ],
    ids=["no-version-heading", "unreleased-heading"],
)
def test_update_changelog_rejects_entry_without_released_version(tmp_path, bad_entry):
    """AC7: an entry that is not a released section is refused, file untouched."""
    changelog = tmp_path / "CHANGELOG.md"
    original = FILE_SHAPES[2]
    changelog.write_text(original, encoding="utf-8")

    with pytest.raises(ValueError):
        update_changelog(changelog, bad_entry)

    assert changelog.read_text(encoding="utf-8") == original


def test_update_changelog_refuses_ambiguous_duplicate_sections(tmp_path):
    """AC8: a file already carrying two sections for the version is not guessed at."""
    changelog = tmp_path / "CHANGELOG.md"
    original = (
        "# Changelog\n\n## [Unreleased]\n\n"
        "## [1.1.0] - 2026-07-27\n\n### Fixed\n- a\n\n"
        "## [1.1.0] - 2026-07-27\n\n### Fixed\n- b\n\n"
        "## [1.0.0] - 2024-01-10\n\n### Added\n- first\n"
    )
    changelog.write_text(original, encoding="utf-8")

    with pytest.raises(ValueError) as excinfo:
        update_changelog(changelog, ENTRY)

    message = str(excinfo.value)
    assert "2 sections" in message
    assert "version 1.1.0" in message
    assert changelog.read_text(encoding="utf-8") == original
