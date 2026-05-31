"""Tests for shared/scripts/tools/aggregate_changelog.py."""

from __future__ import annotations

import re
from pathlib import Path


from tools.aggregate_changelog import (
    CHANGELOG_NAME,
    _find_structural_insertion_line,
    _insert_section,
    _render_versioned_section,
    aggregate,
)
from tools.write_changelog_drop import drop_dir, write_changelog_drop


STANDARD_HEADER = (
    "# Changelog\n"
    "\n"
    "All notable changes to this project will be documented in this file.\n"
    "\n"
    "The format is based on [Keep a Changelog], and this project adheres to SemVer.\n"
    "\n"
)


def _seed_changelog(project: Path, content: str) -> None:
    (project / CHANGELOG_NAME).write_text(content, encoding="utf-8")


def _seed_drops(project: Path, drops: list[tuple[str, str, str]]) -> None:
    """drops: list of (run_id, category, bullet)."""
    for run_id, category, bullet in drops:
        write_changelog_drop(project, run_id, category, bullet)


# ---------------------------------------------------------------------------
# _render_versioned_section
# ---------------------------------------------------------------------------


class TestRender:
    def test_empty_category_map_yields_empty_string(self):
        assert _render_versioned_section("0.3.0", "2026-04-23", {}) == ""

    def test_single_category_renders_correctly(self):
        section = _render_versioned_section(
            "0.3.0",
            "2026-04-23",
            {"Added": [("iterate-2026-04-23-a_001", "New widget")]},
        )
        assert "## [0.3.0] - 2026-04-23" in section
        assert "### Added" in section
        assert "- New widget" in section

    def test_categories_rendered_in_keep_a_changelog_order(self):
        section = _render_versioned_section(
            "0.3.0",
            "2026-04-23",
            {
                "Fixed": [("r_001", "fixed bullet")],
                "Added": [("a_001", "added bullet")],
                "Security": [("s_001", "security bullet")],
            },
        )
        # Added precedes Fixed precedes Security per spec.
        added_idx = section.index("### Added")
        fixed_idx = section.index("### Fixed")
        security_idx = section.index("### Security")
        assert added_idx < fixed_idx < security_idx

    def test_preserves_multiple_bullets_in_drop_order(self):
        section = _render_versioned_section(
            "0.3.0",
            "2026-04-23",
            {
                "Changed": [
                    ("run_001", "first bullet"),
                    ("run_002", "second bullet"),
                    ("run_003", "third bullet"),
                ]
            },
        )
        bullets = re.findall(r"^-\s+(.*)$", section, flags=re.MULTILINE)
        assert bullets == ["first bullet", "second bullet", "third bullet"]

    def test_does_not_double_prefix_bullet_already_starting_with_dash(self):
        section = _render_versioned_section(
            "0.3.0",
            "2026-04-23",
            {"Added": [("r_001", "- already dashed")]},
        )
        assert "- already dashed" in section
        assert "- - already dashed" not in section


# ---------------------------------------------------------------------------
# _find_structural_insertion_line + _insert_section
# ---------------------------------------------------------------------------


class TestStructuralInsert:
    def test_inserts_above_first_version_section(self):
        text = STANDARD_HEADER + "## [0.2.0] - 2026-04-01\n\n- old bullet\n"
        new = _insert_section(text, "## [0.3.0] - 2026-04-23\n\n### Added\n- new\n")
        # New section appears BEFORE the old section.
        new_idx = new.index("## [0.3.0]")
        old_idx = new.index("## [0.2.0]")
        assert new_idx < old_idx
        # Standard header is still the first line.
        assert new.startswith("# Changelog\n")

    def test_does_not_prepend_above_title(self):
        """The classic bug that Gemini flagged: blind prepend would place
        ## [vX] above the # Changelog title. Must NOT happen."""
        text = STANDARD_HEADER + "## [0.2.0] - 2026-04-01\n"
        new = _insert_section(text, "## [0.3.0] - 2026-04-23\n\n### Added\n- x\n")
        first_line = new.splitlines()[0]
        assert first_line == "# Changelog"

    def test_inserts_below_unreleased_when_no_prior_version(self):
        """Keep-a-Changelog convention: [Unreleased] stays on top; new
        versioned releases go BELOW it in descending chronological order."""
        text = STANDARD_HEADER + "## [Unreleased]\n\n- some legacy bullet\n"
        new = _insert_section(text, "## [0.3.0] - 2026-04-23\n\n### Added\n- x\n")
        unr_idx = new.index("## [Unreleased]")
        rel_idx = new.index("## [0.3.0]")
        assert unr_idx < rel_idx
        # The legacy bullet must survive untouched above the new section.
        assert "some legacy bullet" in new
        assert new.index("some legacy bullet") < rel_idx

    def test_inserts_below_unreleased_but_above_prior_version(self):
        """Mixed case: both [Unreleased] and a prior versioned section exist.
        The new version goes above the prior versioned one, and [Unreleased]
        stays on top."""
        text = (
            STANDARD_HEADER
            + "## [Unreleased]\n\n- pending work\n\n"
            + "## [0.2.0] - 2026-04-01\n\n- old release\n"
        )
        new = _insert_section(text, "## [0.3.0] - 2026-04-23\n\n### Added\n- x\n")
        unr_idx = new.index("## [Unreleased]")
        rel_idx = new.index("## [0.3.0]")
        old_idx = new.index("## [0.2.0]")
        assert unr_idx < rel_idx < old_idx

    def test_inserts_after_header_when_no_existing_version(self):
        text = STANDARD_HEADER
        new = _insert_section(text, "## [0.3.0] - 2026-04-23\n\n### Added\n- x\n")
        assert new.startswith("# Changelog\n")
        assert "## [0.3.0]" in new

    def test_empty_file_still_inserts(self):
        new = _insert_section("", "## [0.3.0] - 2026-04-23\n\n### Added\n- x\n")
        assert "## [0.3.0]" in new


def test_find_structural_insertion_line_handles_edge_cases():
    assert _find_structural_insertion_line([]) == 0
    # Only a title + blank line.
    assert _find_structural_insertion_line(["# Changelog", ""]) == 2


# ---------------------------------------------------------------------------
# aggregate() end-to-end
# ---------------------------------------------------------------------------


class TestAggregateEndToEnd:
    def test_happy_path_builds_section_and_cleans_drops(self, tmp_path):
        _seed_changelog(tmp_path, STANDARD_HEADER + "## [0.2.0] - 2026-04-01\n\n- old\n")
        _seed_drops(
            tmp_path,
            [
                ("iterate-2026-04-20-a", "Added", "first added"),
                ("iterate-2026-04-21-b", "Added", "second added"),
                ("iterate-2026-04-22-c", "Fixed", "a fix"),
            ],
        )

        result = aggregate(tmp_path, "0.3.0", release_date="2026-04-23")

        assert result["changelog_updated"] is True
        assert result["version"] == "0.3.0"

        changelog = (tmp_path / CHANGELOG_NAME).read_text(encoding="utf-8")
        assert "## [0.3.0] - 2026-04-23" in changelog
        assert "first added" in changelog
        assert "second added" in changelog
        assert "a fix" in changelog

        # Drops were cleaned up.
        remaining = list(drop_dir(tmp_path).rglob("*.md"))
        assert remaining == []

    def test_dry_run_reports_without_writing(self, tmp_path):
        _seed_changelog(tmp_path, STANDARD_HEADER)
        _seed_drops(tmp_path, [("iterate-2026-04-23-d", "Added", "dry bullet")])

        before = (tmp_path / CHANGELOG_NAME).read_text(encoding="utf-8")
        result = aggregate(
            tmp_path, "0.3.0", release_date="2026-04-23", dry_run=True
        )

        assert result["changelog_updated"] is False
        # Rendered section is in the result even though disk was untouched.
        assert "## [0.3.0] - 2026-04-23" in result["section_written"]
        # Disk is byte-identical.
        after = (tmp_path / CHANGELOG_NAME).read_text(encoding="utf-8")
        assert before == after
        # Drops were NOT deleted in dry-run.
        remaining = list(drop_dir(tmp_path).rglob("*.md"))
        assert len(remaining) == 1

    def test_no_drops_produces_empty_section_and_no_update(self, tmp_path):
        _seed_changelog(tmp_path, STANDARD_HEADER)
        result = aggregate(tmp_path, "0.3.0", release_date="2026-04-23")
        assert result["section_written"] == ""
        assert result["changelog_updated"] is False

    def test_legacy_unreleased_bullets_preserved_and_warned(self, tmp_path, capsys):
        """Brittle markdown-parsing removed entirely. Legacy bullets stay
        untouched, operator gets a stderr warning, new version lands above
        them."""
        legacy_content = (
            STANDARD_HEADER
            + "## [Unreleased]\n"
            + "\n"
            + "### Added\n"
            + "- orphan legacy entry\n"
            + "\n"
            + "## [0.2.0] - 2026-04-01\n"
            + "\n"
            + "- old release\n"
        )
        _seed_changelog(tmp_path, legacy_content)
        _seed_drops(tmp_path, [("iterate-2026-04-23-e", "Added", "new release bullet")])

        result = aggregate(tmp_path, "0.3.0", release_date="2026-04-23")
        assert result["legacy_unreleased_bullets"] == 1

        changelog = (tmp_path / CHANGELOG_NAME).read_text(encoding="utf-8")
        assert "orphan legacy entry" in changelog  # preserved
        assert "new release bullet" in changelog  # aggregated

        captured = capsys.readouterr()
        assert "legacy [Unreleased]" in captured.err
        assert "1 bullet" in captured.err

    def test_selective_cleanup_preserves_drops_written_between_snapshot_and_cleanup(
        self, tmp_path, monkeypatch
    ):
        """A new drop written between snapshot and cleanup must survive. We
        simulate by monkey-patching _snapshot_drop_files to return a subset
        of existing drops; the remaining drops must NOT be deleted."""
        _seed_changelog(tmp_path, STANDARD_HEADER)
        _seed_drops(
            tmp_path,
            [
                ("iterate-2026-04-23-a", "Added", "first"),
                ("iterate-2026-04-23-b", "Added", "second"),
            ],
        )

        # Patch snapshot to only see "first" — "second" simulates a drop
        # written between the snapshot and the cleanup phase.
        import tools.aggregate_changelog as mod
        real_snapshot = mod._snapshot_drop_files

        def partial_snapshot(project_root):
            by_category, processed = real_snapshot(project_root)
            # Drop the 'second' entry from the processed set.
            filtered_processed = [
                p for p in processed if "second" not in p.read_text(encoding="utf-8")
            ]
            filtered_by_category: dict = {}
            for cat, items in by_category.items():
                kept = [(stem, content) for stem, content in items if "second" not in content]
                if kept:
                    filtered_by_category[cat] = kept
            return filtered_by_category, filtered_processed

        monkeypatch.setattr(mod, "_snapshot_drop_files", partial_snapshot)

        aggregate(tmp_path, "0.3.0", release_date="2026-04-23")

        # Only "first" made it into this release.
        changelog = (tmp_path / CHANGELOG_NAME).read_text(encoding="utf-8")
        assert "first" in changelog
        assert "second" not in changelog

        # "second" file must still be on disk for the next release.
        remaining = list(drop_dir(tmp_path).rglob("*.md"))
        assert len(remaining) == 1
        assert "second" in remaining[0].read_text(encoding="utf-8")

    def test_missing_changelog_file_is_created_with_header(self, tmp_path):
        # No seed; aggregate must still produce a valid CHANGELOG.md.
        _seed_drops(tmp_path, [("iterate-2026-04-23-z", "Added", "created")])
        aggregate(tmp_path, "0.3.0", release_date="2026-04-23")

        changelog = (tmp_path / CHANGELOG_NAME).read_text(encoding="utf-8")
        assert changelog.startswith("# Changelog")
        assert "## [0.3.0] - 2026-04-23" in changelog
        assert "created" in changelog

    def test_skips_gitkeep_and_dotfiles(self, tmp_path):
        _seed_changelog(tmp_path, STANDARD_HEADER)
        cat_dir = drop_dir(tmp_path) / "Added"
        cat_dir.mkdir(parents=True)
        (cat_dir / ".gitkeep").write_text("", encoding="utf-8")
        (cat_dir / "_internal.md").write_text("internal", encoding="utf-8")
        _seed_drops(tmp_path, [("iterate-2026-04-23-real", "Added", "real bullet")])

        result = aggregate(tmp_path, "0.3.0", release_date="2026-04-23")
        assert result["changelog_updated"] is True
        changelog = (tmp_path / CHANGELOG_NAME).read_text(encoding="utf-8")
        assert "real bullet" in changelog
        assert "internal" not in changelog

        # Gitkeep + internal not in processed list.
        assert all(".gitkeep" not in p for p in result["processed_files"])
        assert all("_internal" not in p for p in result["processed_files"])
