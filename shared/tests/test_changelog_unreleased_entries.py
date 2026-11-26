"""P8b fix round 1: ``changelog_unreleased.take`` never splits a hand-written entry (FR-01.09 AC09).

A lazy continuation (a plain column-0 line right after the bullet) and a fenced block that opens inside the bullet go
with it; nothing inside a fence is read as a bullet; an entry whose end cannot be told stays whole in ``[Unreleased]``
and is named; lines split on ``\\n`` only, so a U+2028 inside a bullet is text, not a line break.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parents[2] / "shared" / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import changelog_unreleased as cu  # noqa: E402
from tools.aggregate_changelog import _CATEGORY_ORDER  # noqa: E402

pytestmark = pytest.mark.covers("FR-01.09/AC09")

HISTORY = "## [1.2.0] - 2026-01-15\n\n- Old\n"
FENCE = "`" * 3


def _wrap(body: str) -> str:
    return "# Changelog\n\n## [Unreleased]\n\n### Fixed\n\n" + body + "\n" + HISTORY


def test_a_lazy_continuation_at_column_0_moves_with_its_bullet():
    new, moved, left = cu.take(_wrap("- First line\nwrapped lazily at column 0\n- Next\n"), _CATEGORY_ORDER)
    assert moved == {"Fixed": ["First line\nwrapped lazily at column 0", "Next"]} and left == []
    assert "lazily" not in new.split("## [1.2.0]")[0]


def test_a_column_0_fence_right_after_a_bullet_moves_whole_and_its_lines_are_never_bullets():
    body = f"- Fixed the parser\n{FENCE}\n- not a bullet\n### not a heading\n{FENCE}\n- Next\n"
    new, moved, left = cu.take(_wrap(body), _CATEGORY_ORDER)
    assert moved == {"Fixed": [f"Fixed the parser\n{FENCE}\n- not a bullet\n### not a heading\n{FENCE}", "Next"]}
    assert left == [] and "not a bullet" not in new


def test_an_entry_with_a_fence_that_never_closes_stays_whole_and_is_named():
    text = _wrap(f"- Clean one\n- Broken one\n  {FENCE}\n  - inside\n")
    new, moved, left = cu.take(text, _CATEGORY_ORDER)
    assert moved == {"Fixed": ["Clean one"]}
    assert "Broken one" in left and f"- Broken one\n  {FENCE}\n  - inside\n" in new  # never half of it


def test_a_u2028_inside_a_bullet_is_text_not_a_line_break():
    text = _wrap("- Before after\n")
    new, moved, left = cu.take(text, _CATEGORY_ORDER)
    assert moved == {"Fixed": ["Before after"]} and left == [] and " " not in new


def test_crlf_endings_are_kept_on_the_lines_that_stay():
    text = _wrap("- Moves\n").replace("\n", "\r\n")
    new, moved, _left = cu.take(text, _CATEGORY_ORDER)
    assert moved == {"Fixed": ["Moves"]} and "\r\n## [1.2.0]" in new and "\n\n" not in new.replace("\r\n", "")
