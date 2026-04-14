"""Tests for shared/scripts/tools/append_changelog_entry.py."""

from __future__ import annotations

from pathlib import Path

import pytest

from tools.append_changelog_entry import (
    KEEP_A_CHANGELOG_CATEGORIES,
    append_entry,
    find_changelog,
)


def read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# find_changelog
# ---------------------------------------------------------------------------

def test_find_changelog_prefers_project_root(tmp_path):
    proj = tmp_path / "webui"
    proj.mkdir()
    (proj / "CHANGELOG.md").write_text("# changelog\n")
    (tmp_path / "CHANGELOG.md").write_text("# parent\n")
    assert find_changelog(proj) == proj / "CHANGELOG.md"


def test_find_changelog_falls_back_to_parent(tmp_path):
    proj = tmp_path / "webui"
    proj.mkdir()
    (tmp_path / "CHANGELOG.md").write_text("# parent\n")
    assert find_changelog(proj) == tmp_path / "CHANGELOG.md"


def test_find_changelog_returns_project_root_when_neither_exists(tmp_path):
    proj = tmp_path / "webui"
    proj.mkdir()
    assert find_changelog(proj) == proj / "CHANGELOG.md"


# ---------------------------------------------------------------------------
# append_entry — happy paths
# ---------------------------------------------------------------------------

def test_append_entry_creates_changelog_when_missing(tmp_path):
    cl = tmp_path / "CHANGELOG.md"
    result = append_entry(cl, "Added", "First thing")
    assert result["status"] == "created"
    content = read(cl)
    assert "## [Unreleased]" in content
    assert "### Added" in content
    assert "- First thing" in content


def test_append_entry_adds_category_when_missing(tmp_path):
    cl = tmp_path / "CHANGELOG.md"
    cl.write_text("# Changelog\n\n## [Unreleased]\n\n### Fixed\n- Old bug\n")
    append_entry(cl, "Added", "New feature")
    content = read(cl)
    assert "### Added" in content
    assert "- New feature" in content
    assert "- Old bug" in content  # existing content preserved


def test_append_entry_preserves_existing_bullets(tmp_path):
    cl = tmp_path / "CHANGELOG.md"
    cl.write_text(
        "# Changelog\n\n## [Unreleased]\n\n### Added\n- A\n- B\n\n## [v0.1]\n- old\n"
    )
    append_entry(cl, "Added", "C")
    content = read(cl)
    # All three bullets must be present, with C appended last.
    assert "- A" in content
    assert "- B" in content
    assert "- C" in content
    assert content.index("- C") > content.index("- B")
    # Old version not touched
    assert "## [v0.1]" in content
    assert "- old" in content


def test_append_entry_respects_category_order(tmp_path):
    cl = tmp_path / "CHANGELOG.md"
    cl.write_text(
        "# Changelog\n\n## [Unreleased]\n\n### Security\n- CVE fix\n"
    )
    append_entry(cl, "Added", "Feature")
    content = read(cl)
    # Added should come before Security per KaC order
    assert content.index("### Added") < content.index("### Security")


# ---------------------------------------------------------------------------
# append_entry — dedup
# ---------------------------------------------------------------------------

def test_append_entry_dedup_skips_exact_duplicate(tmp_path):
    cl = tmp_path / "CHANGELOG.md"
    cl.write_text(
        "# Changelog\n\n## [Unreleased]\n\n### Fixed\n- Same bug\n"
    )
    result = append_entry(cl, "Fixed", "Same bug")
    assert result["status"] == "dedup"
    # No duplicate appended
    assert read(cl).count("- Same bug") == 1


def test_append_entry_no_dedup_allows_duplicate(tmp_path):
    cl = tmp_path / "CHANGELOG.md"
    cl.write_text(
        "# Changelog\n\n## [Unreleased]\n\n### Fixed\n- Same bug\n"
    )
    append_entry(cl, "Fixed", "Same bug", dedup=False)
    assert read(cl).count("- Same bug") == 2


# ---------------------------------------------------------------------------
# append_entry — validation
# ---------------------------------------------------------------------------

def test_append_entry_rejects_unknown_category(tmp_path):
    cl = tmp_path / "CHANGELOG.md"
    with pytest.raises(ValueError):
        append_entry(cl, "Bogus", "X")


def test_append_entry_does_not_leak_into_released_section(tmp_path):
    cl = tmp_path / "CHANGELOG.md"
    cl.write_text(
        "# Changelog\n\n"
        "## [Unreleased]\n\n### Fixed\n- Open bug\n\n"
        "## [v0.1.0] - 2026-01-01\n\n### Fixed\n- Shipped bug\n"
    )
    append_entry(cl, "Fixed", "New bug")
    content = read(cl)
    # The new bullet must appear before the released version heading
    assert content.index("- New bug") < content.index("## [v0.1.0]")


def test_categories_constant_is_complete():
    assert set(KEEP_A_CHANGELOG_CATEGORIES) == {
        "Added", "Changed", "Deprecated", "Removed", "Fixed", "Security"
    }
