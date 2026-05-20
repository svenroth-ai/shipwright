"""Unit tests for ``shared/scripts/markdown_table.py::escape_cell``.

Lives under ``shared/tests/`` so it runs in the shared test session and
imports ``markdown_table`` from ``shared/scripts/`` (NOT the ``lib/``
namespace, per ADR-045).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SHARED_SCRIPTS = _REPO_ROOT / "shared" / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

from markdown_table import escape_cell  # noqa: E402


def test_escape_cell_passes_plain_text_unchanged() -> None:
    assert escape_cell("hello world") == "hello world"


def test_escape_cell_escapes_pipe() -> None:
    assert escape_cell("a | b") == "a \\| b"


def test_escape_cell_escapes_multiple_pipes() -> None:
    assert escape_cell("(local|tailscale|open)") == "(local\\|tailscale\\|open)"


def test_escape_cell_collapses_lf_to_space() -> None:
    assert escape_cell("line1\nline2") == "line1 line2"


def test_escape_cell_collapses_crlf_to_space() -> None:
    assert escape_cell("line1\r\nline2") == "line1 line2"


def test_escape_cell_collapses_bare_cr_to_space() -> None:
    assert escape_cell("line1\rline2") == "line1 line2"


def test_escape_cell_escapes_backslash_before_pipe() -> None:
    # \ must be doubled BEFORE | is escaped, otherwise an upstream
    # `\\|` would round-trip incorrectly. The desired output is the
    # source `\` rendered as `\\` and the source `|` rendered as `\|`.
    assert escape_cell("a\\|b") == "a\\\\\\|b"


def test_escape_cell_none_returns_empty_string() -> None:
    assert escape_cell(None) == ""


def test_escape_cell_coerces_non_string() -> None:
    assert escape_cell(42) == "42"
    assert escape_cell(True) == "True"


def test_escape_cell_empty_string() -> None:
    assert escape_cell("") == ""


def test_escape_cell_preserves_leading_and_trailing_whitespace() -> None:
    # Markdown table renderers usually strip cell whitespace anyway, but
    # the helper itself must not mangle it — callers depend on
    # `f"| {escape_cell(x)} |"` providing exactly one separator space
    # on each side.
    assert escape_cell("  trimmed  ") == "  trimmed  "


def test_escape_cell_table_row_round_trip() -> None:
    # End-to-end: a row built with escape_cell must split on UN-escaped
    # `|` into exactly the right number of segments.
    cells = ["intent", "A (x|y|z) B", "7/7", "abc1234", "FR-1", "2026-05-20"]
    row = "| " + " | ".join(escape_cell(c) for c in cells) + " |"

    import re
    # Split on a `|` that is not preceded by an odd run of backslashes.
    # For our purposes (single-escape), `(?<!\\)\|` is enough — we never
    # emit `\\\\|`.
    segments = re.split(r"(?<!\\)\|", row)
    # Leading empty + 6 cells + trailing empty = 8 segments.
    assert len(segments) == 8
    assert segments[0] == ""
    assert segments[-1] == ""
    assert [s.strip() for s in segments[1:-1]] == [
        "intent",
        "A (x\\|y\\|z) B",
        "7/7",
        "abc1234",
        "FR-1",
        "2026-05-20",
    ]


@pytest.mark.parametrize(
    "raw,expected",
    [
        # 8 boundary categories from references/boundary-probes.md
        # applicable to a machine-only markdown producer:
        ("normal", "normal"),                          # 1. plain
        ("a|b", "a\\|b"),                              # 2. pipe (the bug)
        ("a\nb", "a b"),                               # 3. newline
        ("a\r\nb", "a b"),                             # 4. CRLF (Windows)
        ("a\\b", "a\\\\b"),                            # 5. backslash
        ("", ""),                                      # 6. empty
        ("   ", "   "),                                # 7. whitespace-only
        ("a|b\nc", "a\\|b c"),                         # 8. combined
    ],
)
def test_escape_cell_boundary_categories(raw: str, expected: str) -> None:
    assert escape_cell(raw) == expected
