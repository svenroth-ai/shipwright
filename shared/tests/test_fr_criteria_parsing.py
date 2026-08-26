"""Pins ``lib.fr_criteria``'s own block-termination and bullet-semantics rules
(iterate-2026-08-25-fr-criteria-parser-pin, merged from trg-968e4d87 +
trg-467b7b2f).

PR #648 unified three FR-criteria readers onto ``lib.fr_criteria`` and, in
doing so, widened parsing behaviour past what any of the three predecessors
accepted. Stage-2 code review flagged two widenings as deliberate but
UNPINNED: neither had a test of its own, so nothing stops a future edit from
"simplifying" either rule under the belief it is accidental. This file is
that pin — each test is the documentation.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))

from lib import fr_criteria  # noqa: E402


# ---------------------------------------------------------------------------
# (1) iter_anchored_blocks — two block-termination rules (trg-968e4d87 #1)
# ---------------------------------------------------------------------------

def test_a_same_rank_non_fr_heading_ends_a_heading_anchored_block():
    """A heading anchor's block ends at the next heading of the SAME OR
    HIGHER rank even when that heading is NOT itself FR-shaped — e.g. a
    sibling ``## Constraints`` section right after ``## FR-01.01``. Without
    this, an FR's block would swallow every unrelated section that follows
    it until the next FR (or the document's end)."""
    doc = (
        "## FR-01.01 — Title\n\n"
        "- (E) real criterion\n\n"
        "## Constraints\n\n"
        "- (E) this bullet belongs to Constraints, not FR-01.01\n"
    )
    blocks = list(fr_criteria.iter_anchored_blocks(doc))
    assert len(blocks) == 1
    fr_id, lines = blocks[0]
    assert fr_id == "FR-01.01"
    joined = "\n".join(lines)
    assert "real criterion" in joined
    assert "Constraints" not in joined
    assert "belongs to Constraints" not in joined


def test_a_lower_rank_non_fr_heading_also_ends_the_block():
    """The same rule at the boundary case: a LOWER rank (fewer ``#``, i.e.
    outranking) non-FR heading ends the block too, not just an equal one."""
    doc = (
        "### FR-01.01 — Title\n\n"
        "- (E) real criterion\n\n"
        "## Section Above It\n\n"
        "- (E) not FR-01.01's\n"
    )
    fr_id, lines = next(fr_criteria.iter_anchored_blocks(doc))
    assert fr_id == "FR-01.01"
    assert "not FR-01.01" not in "\n".join(lines)


def test_a_deeper_non_fr_heading_does_not_end_the_block():
    """The converse of the two tests above, to prove the rank comparison is
    real and not "any heading ends it": a DEEPER (higher ``#`` count) non-FR
    heading is a subsection and stays inside the block."""
    doc = (
        "## FR-01.01 — Title\n\n"
        "#### Notes\n\n"
        "- (E) still inside FR-01.01\n"
    )
    fr_id, lines = next(fr_criteria.iter_anchored_blocks(doc))
    assert fr_id == "FR-01.01"
    assert "still inside FR-01.01" in "\n".join(lines)


def test_an_fr_shaped_bold_line_truncates_a_heading_anchored_block():
    """A criterion line that happens to start with ``**FR-XX.YY`` (a second
    FR anchored in bold form, right after a heading-anchored one, with no
    heading of its own) still cuts the first block off — the SECOND
    termination rule, independent of heading rank."""
    doc = (
        "## FR-01.01 — Title\n\n"
        "- (E) real criterion\n\n"
        "**FR-01.02: Name**\n"
        "- [ ] belongs to FR-01.02, not FR-01.01\n"
    )
    blocks = list(fr_criteria.iter_anchored_blocks(doc))
    assert [fr_id for fr_id, _ in blocks] == ["FR-01.01", "FR-01.02"]
    first_lines = "\n".join(blocks[0][1])
    assert "real criterion" in first_lines
    assert "belongs to FR-01.02" not in first_lines


# ---------------------------------------------------------------------------
# (2) group_i_criteria (I6) bullet semantics widening (trg-968e4d87 #2)
# ---------------------------------------------------------------------------

def test_numbered_list_bullets_count_as_criteria():
    """``1.`` and ``1)`` numbered-list markers are accepted as bullets, not
    just ``-``/``*``/``+`` — I6's shared reader widened past dash-only."""
    lines = [
        "1. Given a change, when it runs, then it works.",
        "2) Given a failure, when it runs, then it stops.",
    ]
    assert fr_criteria.criteria_texts(lines) == [
        "Given a change, when it runs, then it works.",
        "Given a failure, when it runs, then it stops.",
    ]


def test_a_placeholder_bullet_is_dropped_not_counted_as_a_criterion():
    """A bullet whose text reduces to a placeholder token (``TBD``, ``N/A``,
    …) once punctuation/whitespace is stripped is not a real criterion."""
    lines = ["- TBD", "- N/A", "- Real criterion text."]
    assert fr_criteria.criteria_texts(lines) == ["Real criterion text."]


def test_a_continuation_line_joins_onto_the_bullet_that_opened_it():
    """An indented line right after a bullet extends that bullet's text
    (wrapped acceptance-criterion prose), rather than starting a new,
    separate criterion or being dropped."""
    lines = [
        "- (E) Given a change spanning two lines,",
        "  when it wraps, then it still joins as one criterion.",
    ]
    assert fr_criteria.criteria_texts(lines) == [
        "Given a change spanning two lines, when it wraps, "
        "then it still joins as one criterion.",
    ]


# I6's OWN entry point (``group_i_criteria.has_criteria``) seeing this same
# widened bullet semantics is pinned in
# ``integration-tests/test_fr_criteria_three_way_convergence.py`` — this
# root cannot import the compliance plugin's ``scripts`` package without
# giving it a second identity in the pytest process (ADR-044; see that
# file's module docstring).
