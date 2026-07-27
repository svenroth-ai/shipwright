"""Shared CHANGELOG.md corpus and preservation helpers.

Not a test module — imported by test_changelog.py and
test_changelog_preservation.py so both stay within the size budget.
"""

ENTRY = "## [1.1.0] - 2026-07-27\n\n### Fixed\n- fix: something\n"

# Real-world CHANGELOG shapes the writer must never destroy content in.
FILE_SHAPES = [
    # 1. hand-written history, no [Unreleased] marker (brownfield: the reported bug)
    "# Release History\n\nNotes kept by hand since 2019.\n\n"
    "## [1.0.0] - 2024-01-10\n\n### Added\n- first stable release\n\n"
    "## [0.9.0] - 2023-11-02\n\n### Fixed\n- an early bug\n",
    # 2. marker with pending bullets, no released section yet
    "# Changelog\n\n## [Unreleased]\n\n- feat: pending one\n- fix: pending two\n",
    # 3. marker + released section (the classic, already-working shape)
    "# Changelog\n\n## [Unreleased]\n\n## [1.0.0] - 2024-01-10\n\n### Added\n- first\n",
    # 4. title and prose only, no sections at all
    "# Changelog\n\nWe write these by hand.\n",
    # 5. bare released section, no title
    "## [1.0.0] - 2024-01-10\n\n### Added\n- first\n",
    # 6. non-bracket level-2 headings
    "# History\n\n## Notes\n\nSome free text nobody wants deleted.\n",
    # 7. marker with bullets AND a released section
    "# Changelog\n\n## [Unreleased]\n\n- feat: pending\n\n"
    "## [1.0.0] - 2024-01-10\n\n### Added\n- first\n",
    # 8. no trailing newline
    "# Changelog\n\n## [1.0.0] - 2024-01-10\n\n### Added\n- first",
    # 9. canonical Keep-a-Changelog link-reference footer below the last section
    "# Changelog\n\n## [1.0.0] - 2024-01-10\n\n### Added\n- first\n\n"
    "[1.0.0]: https://example.invalid/releases/tag/v1.0.0\n",
    # 10. no heading and no paragraph break — reaches the end-of-file arm
    "# Changelog",
    # 11. UTF-8 BOM ahead of the first heading
    "﻿## [1.0.0] - 2024-01-10\n\n### Added\n- first\n",
    # 12. prose trailing the last section (loses content on re-run if the
    #     replaced span is not bounded)
    "# Changelog\n\n## [1.0.0] - 2024-01-10\n\n### Added\n- first\n\n"
    "Maintained by the release team.\n",
]

SHAPE_IDS = [str(i) for i in range(1, len(FILE_SHAPES) + 1)]


def write_exact(path, text):
    """Write `text` byte-exactly — no platform newline translation.

    Plain `write_text` would rewrite every "\\n" as CRLF on Windows, which
    would make the byte-preservation assertions compare against something the
    test never actually wrote.
    """
    path.write_text(text, encoding="utf-8", newline="")


def significant_lines(text):
    """Non-blank lines, for coarse 'nothing was dropped' checks."""
    return [line for line in text.splitlines() if line.strip()]


def assert_preserved(original, content):
    """Every original line survives, in order, byte-for-byte.

    Compares with `keepends=True`, so a dropped trailing blank line or a
    changed line ending is a failure — a non-blank-line comparison sees
    neither. The single documented exception: when the entry is appended at
    end of file, the previously-unterminated final line necessarily gains its
    terminator. That adds a byte; it never removes content.
    """
    # A BOM marks the file, not a line: it stays attached to whatever line ends
    # up first, so it is compared by test_preserves_utf8_bom, not here.
    remaining = iter(content.lstrip("﻿").splitlines(keepends=True))
    original_lines = original.lstrip("﻿").splitlines(keepends=True)
    for index, line in enumerate(original_lines):
        last_unterminated = (
            index == len(original_lines) - 1 and not line.endswith("\n")
        )
        if last_unterminated:
            found = any(c.rstrip("\r\n") == line for c in remaining)
        else:
            found = any(c == line for c in remaining)
        assert found, f"lost or reordered line: {line!r}"
