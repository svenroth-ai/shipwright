"""Hand-written ``## [Unreleased]`` entries move into the release (pilot P8b, operator decision Q5, FR-01.09 AC09).

Subject: ``shared/scripts/changelog_unreleased.py`` and ``aggregate_changelog.aggregate(move_unreleased=True)``.
Old behaviour: the aggregator never touched ``[Unreleased]``; it only named the bullets in a stderr WARNING, so a reader of
the release never saw them. Now a bullet under a category heading moves into that category of the new section and leaves
``[Unreleased]``; a bullet under no such heading stays and is still named (never placed by a guess); the dry run changes
nothing and its ``section_preview`` marks the moved ones ``(hand-written)``.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parents[2] / "shared" / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import changelog_unreleased as cu  # noqa: E402
from tools.aggregate_changelog import _CATEGORY_ORDER, AggregatorError, aggregate  # noqa: E402
from tools.write_changelog_drop import write_changelog_drop  # noqa: E402

pytestmark = pytest.mark.covers("FR-01.09/AC09")

HISTORY = "## [1.2.0] - 2026-01-15\n\n### Added\n\n- Earlier feature\n"
UNRELEASED = ("# Changelog\n\n## [Unreleased]\n\n### Added\n\n- Hand one\n  wrapped on a second line\n- Hand two\n\n"
              "### Breaking Changes\n\n- Not a category the release renders\n\n### Fixed\n\n- Hand fix\n\n" + HISTORY)


def _project(tmp_path: Path, text: str) -> Path:
    (tmp_path / "CHANGELOG.md").write_text(text, encoding="utf-8")
    write_changelog_drop(tmp_path, "r-1", "Added", "From a drop")
    return tmp_path


def test_take_moves_categorised_bullets_with_their_continuations_and_keeps_the_rest():
    text, moved, left = cu.take(UNRELEASED, _CATEGORY_ORDER)
    assert moved == {"Added": ["Hand one\n  wrapped on a second line", "Hand two"], "Fixed": ["Hand fix"]}
    assert left == ["Not a category the release renders"]
    assert text == ("# Changelog\n\n## [Unreleased]\n\n### Breaking Changes\n\n- Not a category the release renders\n\n" + HISTORY)


@pytest.mark.parametrize("text", ["# Changelog\n\n" + HISTORY, "# Changelog\n\n## [Unreleased]\n\n- No heading one\n\n" + HISTORY])
def test_take_changes_nothing_without_a_categorised_bullet(text):
    assert cu.take(text, _CATEGORY_ORDER)[:2] == (text, {})


def test_the_release_takes_the_hand_written_entries_after_the_drops_and_empties_unreleased(tmp_path):
    root = _project(tmp_path, UNRELEASED)
    out = aggregate(root, "1.3.0", release_date="2026-11-25", move_unreleased=True)
    text = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    assert text.startswith("# Changelog\n\n## [Unreleased]\n\n### Breaking Changes\n\n- Not a category the release renders\n\n## [1.3.0]")
    assert "### Added\n\n- From a drop\n- Hand one\n  wrapped on a second line\n- Hand two\n\n### Fixed\n\n- Hand fix\n" in text
    assert text.count("Hand two") == 1 and "(hand-written)" not in text
    assert out["hand_written_entries"][-1] == {"category": "Fixed", "text": "Hand fix"}
    assert out["legacy_unreleased_bullet_texts"] == ["Not a category the release renders"]


def test_the_dry_run_marks_them_and_writes_nothing(tmp_path):
    root = _project(tmp_path, UNRELEASED)
    before = (root / "CHANGELOG.md").read_bytes()
    out = aggregate(root, "1.3.0", release_date="2026-11-25", move_unreleased=True, dry_run=True)
    assert (root / "CHANGELOG.md").read_bytes() == before
    assert "- From a drop\n- Hand one (hand-written)\n  wrapped on a second line\n- Hand two (hand-written)" in out["section_preview"]
    assert "(hand-written)" not in out["section_written"] and "- Hand two\n" in out["section_written"]


def test_without_the_flag_the_aggregator_still_only_names_them(tmp_path, capsys):
    root = _project(tmp_path, UNRELEASED)
    out = aggregate(root, "1.3.0", release_date="2026-11-25")
    assert out["hand_written_entries"] == [] and len(out["legacy_unreleased_bullet_texts"]) == 4
    assert "## [Unreleased]\n\n### Added\n\n- Hand one" in (root / "CHANGELOG.md").read_text(encoding="utf-8")


def test_hand_written_entries_alone_make_a_release_and_a_rerun_converges(tmp_path):
    (tmp_path / "CHANGELOG.md").write_text(UNRELEASED, encoding="utf-8")
    out = aggregate(tmp_path, "1.3.0", release_date="2026-11-25", move_unreleased=True, fail_if_empty=True)
    assert out["section_action"] == "inserted" and len(out["hand_written_entries"]) == 3
    again = aggregate(tmp_path, "1.3.0", release_date="2026-11-25", move_unreleased=True, fail_if_empty=True)
    assert again["section_action"] == "none" and again["changelog_updated"] is False


def test_a_bullet_with_a_blank_line_inside_moves_whole():
    text = "# Changelog\n\n## [Unreleased]\n\n### Fixed\n\n- First paragraph\n\n  second paragraph\n- Next\n\n" + HISTORY
    new, moved, left = cu.take(text, _CATEGORY_ORDER)
    assert moved == {"Fixed": ["First paragraph\n\n  second paragraph", "Next"]} and left == []
    assert "paragraph" not in new.split("## [1.2.0]")[0]


def test_an_interrupted_mixed_release_refuses_on_the_rerun_and_changes_nothing(tmp_path):
    """Pinned trade-off of Q5 (FINDINGS D92): once the section took hand-written entries, the drops alone no longer render
    it, so a run interrupted before it consumed the drops is a hand reconcile, never a silent re-render."""
    root = _project(tmp_path, UNRELEASED)
    drops = {p: p.read_bytes() for p in (root / "CHANGELOG-unreleased.d").rglob("*.md")}
    aggregate(root, "1.3.0", release_date="2026-11-25", move_unreleased=True)
    for path, data in drops.items():  # the interruption: the section is written, the drops were never consumed
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    written = (root / "CHANGELOG.md").read_bytes()
    with pytest.raises(AggregatorError):
        aggregate(root, "1.3.0", release_date="2026-11-25", move_unreleased=True)
    assert (root / "CHANGELOG.md").read_bytes() == written and all(p.read_bytes() == d for p, d in drops.items())
