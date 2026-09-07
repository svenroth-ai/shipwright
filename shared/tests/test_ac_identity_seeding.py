"""Registry-seeding regression coverage for ``lib.ac_identity.mint()``'s
Pass 1 (``_ac_blocks.iter_all_bullet_positions``) — three rounds of
code/doubt review, each surfacing a different way an already-assigned
``[ACnn]`` marker could go unseen by seeding.

Split out of ``test_ac_identity.py`` / ``test_ac_identity_markers.py``
purely to keep all three files under the 300-LOC bloat-baseline threshold —
same content that would otherwise sit in one file, not a different subject.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))

from lib import ac_identity  # noqa: E402


def test_seeding_sees_a_marker_outside_the_leading_bullet_run():
    """Code review round 3 (HIGH): the seed pass used to reuse
    ``iter_bullet_positions``, gated to the block's contiguous LEADING
    bullet run -- the same gate minting needs so it never stamps an id
    ``read()`` can't see. But a prose line between two bullets ends that
    leading run (`_ac_blocks._leading_bullet_run_indices`), so the second
    bullet's existing ``[AC01]`` marker was invisible to seeding with a
    lost/empty registry. mint() then re-minted the SAME number onto the
    first, still-unmarked bullet -- the exact "never reused" violation the
    seed pass exists to prevent, and the document became permanently
    un-mintable (DuplicateAcIdError) as soon as the prose line was later
    removed. Seeding must see every bullet in the block, not just the
    leading run; minting stays gated to the leading run."""
    prose_breaks_the_leading_run = (
        "### FR-10.01 — Title\n\n"
        "- (E) A first, not-yet-marked criterion.\n\n"
        "Some prose note that ends the leading bullet run.\n\n"
        "- (E) [AC01] A second criterion, already marked.\n"
    )
    result = ac_identity.mint(prose_breaks_the_leading_run, registry={})
    assert result.assigned == (("FR-10.01", "AC02"),)
    assert "[AC02] A first, not-yet-marked criterion." in result.content
    assert "[AC01] A second criterion, already marked." in result.content
    assert result.registry == {"FR-10.01": 2}

    # Re-minting the result is a no-op: no duplicate, nothing reissued.
    again = ac_identity.mint(result.content, result.registry)
    assert again.assigned == ()
    assert again.content == result.content


def test_seeding_does_not_credit_a_nested_frs_own_bullets_to_the_parent():
    """Code review round 4 (HIGH), regression from the round-3 fix above:
    ``_iter_heading_blocks_by_index`` deliberately runs a parent FR's block
    through a NESTED, deeper-rank FR heading (mirrors
    ``fr_criteria.iter_anchored_blocks``'s own overlap, exercised on the same
    fixture shape by
    ``test_layer_coverage_criteria_anchoring.test_a_nested_fr_heading_still_
    gets_its_own_digest_entry``) -- harmless for ``read()``, whose
    ``block_criteria(strict=True)`` only ever reaches the LEADING run and so
    never sees past the nested heading. But the ungated
    ``iter_all_bullet_positions`` scanned the FULL block range, so a nested
    FR's own already-minted bullet was credited to the PARENT's fr_id during
    seeding. Each FR restarts its own AC numbering at 1, so the nested
    block's first marker is almost always ``[AC01]`` too -- colliding with
    the parent's own real ``[AC01]`` and raising a false
    ``DuplicateAcIdError`` on every re-mint of an already-minted
    nested-heading document, breaking the very idempotency guarantee the
    round-3 fix exists to protect."""
    already_minted_with_nesting = (
        "### FR-01.01 — Parent\n\n"
        "- (E) [AC01] Parent criterion one.\n\n"
        "#### FR-01.02 — Nested\n\n"
        "- (E) [AC01] Nested criterion one.\n"
    )
    result = ac_identity.mint(
        already_minted_with_nesting, registry={"FR-01.01": 1, "FR-01.02": 1}
    )
    assert result.assigned == ()
    assert result.content == already_minted_with_nesting
    assert result.registry == {"FR-01.01": 1, "FR-01.02": 1}


def test_seeding_sees_a_marker_past_a_non_fr_heading_in_the_same_block():
    """Doubt-review round 4b (HIGH), regression from the round-4 fix above:
    that fix stopped the seed scan at ANY heading line to exclude a nested
    FR's own bullets -- but ``_iter_heading_blocks_by_index`` only treats an
    FR-SHAPED heading of same-or-higher rank as a block boundary, so a
    non-FR heading (e.g. a plain ``#### Notes`` subsection) interposed
    between two bullets of the SAME FR block is not a boundary at all.
    Stopping there blinded seeding to a real, already-marked bullet sitting
    past it -- the exact round-3 failure mode (a marker outside the seed
    pass's scan range lets a lost/empty registry reissue its number), just
    triggered by an interposed heading instead of an interposed prose
    paragraph. The fix scopes the stop condition to FR-shaped headings only,
    so seeding keeps scanning through a non-FR heading (like it already does
    through prose) while still stopping at a genuine nested FR heading."""
    non_fr_heading_breaks_the_scan = (
        "## FR-09.01 — Title\n"
        "- (E) A first, not-yet-marked criterion.\n\n"
        "#### Notes\n\n"
        "- (E) [AC01] A marker embedded past a non-FR heading.\n"
    )
    result = ac_identity.mint(non_fr_heading_breaks_the_scan, registry={})
    assert result.assigned == (("FR-09.01", "AC02"),)
    assert "[AC02] A first, not-yet-marked criterion." in result.content
    assert "[AC01] A marker embedded past a non-FR heading." in result.content
    assert result.registry == {"FR-09.01": 2}

    # Re-minting the result is a no-op: no duplicate, nothing reissued.
    again = ac_identity.mint(result.content, result.registry)
    assert again.assigned == ()
    assert again.content == result.content
