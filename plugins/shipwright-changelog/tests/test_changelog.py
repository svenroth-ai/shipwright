"""Tests for changelog module."""


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
