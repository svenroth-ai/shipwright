"""Byte-preservation properties of update_changelog (trg-6690d175).

The writer rewrites a user-authored file in place, so these tests assert on
what lands on disk rather than on what the function returns.
"""

import pytest
from changelog_corpus import (
    ENTRY,
    FILE_SHAPES,
    SHAPE_IDS,
    assert_preserved,
    write_exact,
)

from lib import changelog as changelog_module
from lib.changelog import update_changelog

REVISED = "## [1.1.0] - 2026-07-27\n\n### Added\n- feat: extra\n\n### Fixed\n- fix: revised\n"


@pytest.mark.parametrize("original", FILE_SHAPES, ids=SHAPE_IDS)
def test_insert_never_loses_existing_content(tmp_path, original):
    """One run: no shape may lose a byte, and the entry lands exactly once."""
    changelog = tmp_path / "CHANGELOG.md"
    write_exact(changelog, original)

    content = update_changelog(changelog, ENTRY)

    assert_preserved(original, content)
    assert content.count("## [1.1.0]") == 1


@pytest.mark.parametrize("original", FILE_SHAPES, ids=SHAPE_IDS)
def test_rerun_never_loses_existing_content(tmp_path, original):
    """Two runs: the replacement path must preserve just as much as insertion.

    This is the path that deletes a span, so it is the one that can lose data.
    Running the corpus only once left it entirely uncovered.
    """
    changelog = tmp_path / "CHANGELOG.md"
    write_exact(changelog, original)

    first = update_changelog(changelog, ENTRY)
    second = update_changelog(changelog, ENTRY)

    assert_preserved(original, second)
    assert second == first, "re-running the same entry is not a fixed point"
    assert second.count("## [1.1.0]") == 1


@pytest.mark.parametrize("original", FILE_SHAPES, ids=SHAPE_IDS)
def test_revised_rerun_never_loses_existing_content(tmp_path, original):
    """Replacing with a *different* entry for the same version keeps the file."""
    changelog = tmp_path / "CHANGELOG.md"
    write_exact(changelog, original)

    update_changelog(changelog, ENTRY)
    content = update_changelog(changelog, REVISED)

    assert_preserved(original, content)
    assert content.count("## [1.1.0]") == 1
    assert "- fix: revised" in content
    assert "- fix: something" not in content


def test_replace_preserves_trailing_link_reference_footer(tmp_path):
    """The canonical Keep-a-Changelog footer sits below the last section.

    Bounding the replaced span at 'next ## heading or EOF' swallows it.
    """
    changelog = tmp_path / "CHANGELOG.md"
    original = (
        "# Changelog\n\n## [1.1.0] - 2026-07-27\n\n### Fixed\n- fix: original\n\n"
        "[1.1.0]: https://example.invalid/releases/tag/v1.1.0\n"
        "[Unreleased]: https://example.invalid/compare/v1.1.0...HEAD\n"
    )
    write_exact(changelog, original)

    content = update_changelog(changelog, REVISED)

    assert "[1.1.0]: https://example.invalid/releases/tag/v1.1.0" in content
    assert "[Unreleased]: https://example.invalid/compare/v1.1.0...HEAD" in content
    assert "- fix: revised" in content
    assert content.count("## [1.1.0]") == 1


def test_replace_preserves_trailing_prose(tmp_path):
    """Prose below the last section is not part of it and must survive."""
    changelog = tmp_path / "CHANGELOG.md"
    original = "# Changelog\n\nWe write these by hand.\n"
    write_exact(changelog, original)

    first = update_changelog(changelog, ENTRY)
    second = update_changelog(changelog, ENTRY)

    assert "We write these by hand." in second
    assert second == first


def test_preserves_utf8_bom(tmp_path):
    """A BOM must not blind the parser, and must survive the rewrite."""
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_bytes(
        "﻿## [1.0.0] - 2024-01-10\n\n### Added\n- first\n".encode("utf-8")
    )

    update_changelog(changelog, ENTRY)
    update_changelog(changelog, ENTRY)

    raw = changelog.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf"), "BOM was dropped"
    text = raw.decode("utf-8-sig")
    assert "### Added" in text and "- first" in text
    assert text.count("## [1.1.0]") == 1
    assert text.index("## [1.1.0]") < text.index("## [1.0.0]")


def test_preserves_lf_line_endings(tmp_path):
    """An LF-authored file must not be rewritten wholesale to CRLF."""
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_bytes(
        b"# Changelog\n\n## [1.0.0] - 2024-01-10\n\n### Added\n- first\n"
    )

    update_changelog(changelog, ENTRY)

    assert b"\r\n" not in changelog.read_bytes()


def test_preserves_crlf_line_endings(tmp_path):
    """A CRLF-authored file keeps CRLF throughout — no mixed endings."""
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_bytes(
        b"# Changelog\r\n\r\n## [1.0.0] - 2024-01-10\r\n\r\n### Added\r\n- first\r\n"
    )

    update_changelog(changelog, ENTRY)

    raw = changelog.read_bytes()
    assert raw.count(b"\n") == raw.count(b"\r\n"), "bare LF introduced into a CRLF file"


def test_failed_write_leaves_the_original_intact(tmp_path, monkeypatch):
    """A write that dies mid-flight must not leave a truncated history.

    A plain in-place write truncates before writing, so the operator's whole
    file would be gone. Failing the atomic replace proves the original is still
    on disk and no temp file is orphaned.
    """
    changelog = tmp_path / "CHANGELOG.md"
    original = FILE_SHAPES[2]
    write_exact(changelog, original)

    def explode(*_args, **_kwargs):
        raise OSError("simulated: no space left on device")

    monkeypatch.setattr(changelog_module.os, "replace", explode)

    with pytest.raises(OSError):
        update_changelog(changelog, ENTRY)

    with changelog.open("r", encoding="utf-8", newline="") as handle:
        assert handle.read() == original
    assert list(tmp_path.glob(".changelog-*")) == [], "temp file left behind"


def test_rejects_entry_with_more_than_one_section(tmp_path):
    """An entry must be exactly one section, else replacement is ambiguous."""
    changelog = tmp_path / "CHANGELOG.md"
    original = FILE_SHAPES[2]
    write_exact(changelog, original)

    with pytest.raises(ValueError) as excinfo:
        update_changelog(
            changelog,
            "## [1.1.0] - 2026-07-27\n\n- a\n\n## [1.0.5] - 2026-07-27\n\n- b\n",
        )

    assert "1.1.0" in str(excinfo.value)
    assert changelog.read_text(encoding="utf-8") == original
