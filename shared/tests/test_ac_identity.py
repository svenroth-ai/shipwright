"""Pins ``lib.ac_identity`` — the AC-id minter + reader for the shipped FR
heading+bullet shape (campaign req3-04c-ac-identity-wave2, sub-iterate P3.1).

Doubles as the golden corpus the sub-iterate's own acceptance criteria call
for: each fixture below is a small, self-contained sample of the shipped
shape, and every test asserts the exact minted output — a diff in any of
these numbers is a behaviour change in the minter, not a cosmetic edit.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))

from lib import ac_identity  # noqa: E402

# ---------------------------------------------------------------------------
# Golden corpus fixtures — the shipped shape and its edge cases.
# ---------------------------------------------------------------------------

FRESH_FR = (
    "### FR-01.11 — /shipwright-iterate\n\n"
    "- (E) Given a change described in ordinary words, when it is picked up,\n"
    "  then its kind and size are detected.\n"
    "- (E) Given a feature or a change, when it is classified, then it\n"
    "  records whether it adds, modifies, removes or leaves the requirements\n"
    "  untouched.\n"
    "- (E) Given a change of medium size or larger, when it is finished, then\n"
    "  a real surface is driven through a running system.\n"
)

TWO_FRS = (
    "### FR-01.01 — /shipwright-run\n\n"
    "- (E) Given a described change, when the pipeline is run, then the\n"
    "  phases are carried out in order.\n\n"
    "### FR-01.02 — /shipwright-project\n\n"
    "- (E) Given a project description, when setup is declared finished,\n"
    "  then a catalogue of requirements exists.\n"
)

WITH_CHECKBOX = "### FR-02.01 — Title\n\n- [ ] Given a thing, when it happens, then it holds.\n"

WITH_FOOTNOTE = (
    "### FR-03.01 — Title\n\n"
    "- (E) Given a thing, when it happens, then it holds.\n"
    "  (iterate-2026-01-01-example)\n"
)

WITH_PLACEHOLDER = (
    "### FR-04.01 — Title\n\n"
    "- TBD\n"
    "- (E) Given a real thing, when it happens, then it holds.\n"
)


# ---------------------------------------------------------------------------
# mint() — fresh assignment, in document order, zero-padded.
# ---------------------------------------------------------------------------

def test_fresh_fr_mints_three_ids_in_document_order():
    result = ac_identity.mint(FRESH_FR)
    assert result.assigned == (
        ("FR-01.11", "AC01"),
        ("FR-01.11", "AC02"),
        ("FR-01.11", "AC03"),
    )
    assert result.registry == {"FR-01.11": 3}
    assert "[AC01] Given a change described in ordinary words" in result.content
    assert "[AC02] Given a feature or a change" in result.content
    assert "[AC03] Given a change of medium size" in result.content


def test_two_frs_number_independently():
    result = ac_identity.mint(TWO_FRS)
    assert result.assigned == (("FR-01.01", "AC01"), ("FR-01.02", "AC01"))
    assert result.registry == {"FR-01.01": 1, "FR-01.02": 1}


def test_marker_sits_after_checkbox_decoration():
    """Round-tripped, not just minted (external code review, 2026-09-06
    round 2, GLM low): read() relies entirely on fr_criteria.block_criteria
    stripping the checkbox before parse_marker sees the text -- if that ever
    changed, read() would silently stop pairing this shape with its id and
    no test would fail."""
    result = ac_identity.mint(WITH_CHECKBOX)
    assert "- [ ] [AC01] Given a thing" in result.content
    assert ac_identity.read(result.content, "FR-02.01") == [
        ("AC01", "Given a thing, when it happens, then it holds.")
    ]


def test_marker_does_not_disturb_a_trailing_footnote():
    result = ac_identity.mint(WITH_FOOTNOTE)
    assert "[AC01] Given a thing, when it happens, then it holds." in result.content
    assert "(iterate-2026-01-01-example)" in result.content
    # the footnote is a continuation line of the SAME bullet, so it joins
    # onto the criterion text exactly like any other wrapped second line.
    assert ac_identity.read(result.content, "FR-03.01") == [
        ("AC01", "Given a thing, when it happens, then it holds. (iterate-2026-01-01-example)")
    ]


def test_a_placeholder_bullet_is_still_minted_its_own_id():
    """A `TBD` slot gets an identity immediately -- the id names the SLOT,
    not the (not yet written) wording. This is a deliberate, DEFERRED trade
    (`ac_identity`'s "One known, deferred effect" docstring section): once
    minted, `"[AC01] TBD"` no longer collapses to `fr_criteria`'s bare-
    placeholder token set (see `test_mint_and_read_agree_on_a_duplicate_
    split_across_a_placeholder` in test_ac_identity_markers.py), so a minted
    placeholder becomes a real criterion to every OTHER `fr_criteria` caller
    -- inert today since this run never mints a real, gate-read document."""
    result = ac_identity.mint(WITH_PLACEHOLDER)
    assert result.assigned == (("FR-04.01", "AC01"), ("FR-04.01", "AC02"))
    assert "[AC01] TBD" in result.content
    assert "[AC02] Given a real thing" in result.content


# ---------------------------------------------------------------------------
# Idempotency + never-renumbered — the sub-iterate's hard acceptance criteria.
# ---------------------------------------------------------------------------

def test_rerunning_the_minter_on_its_own_output_is_a_no_op():
    once = ac_identity.mint(FRESH_FR)
    twice = ac_identity.mint(once.content, once.registry)
    assert twice.content == once.content
    assert twice.assigned == ()
    assert twice.registry == once.registry


def test_inserting_a_bullet_in_the_middle_never_renumbers_existing_ids():
    once = ac_identity.mint(FRESH_FR)
    lines = once.content.split("\n")
    insert_at = next(i for i, line in enumerate(lines) if "[AC02]" in line)
    lines.insert(insert_at, "- (E) A brand new criterion inserted in the middle.")
    mutated = "\n".join(lines)

    again = ac_identity.mint(mutated, once.registry)

    assert "[AC01] Given a change described in ordinary words" in again.content
    assert "[AC02] Given a feature or a change" in again.content
    assert "[AC03] Given a change of medium size" in again.content
    # the new bullet gets the NEXT free number, not squeezed between 01/02
    assert again.assigned == (("FR-01.11", "AC04"),)
    assert "[AC04] A brand new criterion inserted in the middle." in again.content


def test_deleting_a_minted_bullet_never_frees_its_number():
    once = ac_identity.mint(FRESH_FR)
    # Delete the AC02 bullet's two lines (its wrapped continuation too).
    lines = [
        line for line in once.content.split("\n")
        if "[AC02]" not in line and "records whether it adds" not in line
    ]
    mutated = "\n".join(lines)

    again = ac_identity.mint(mutated, once.registry)  # registry remembers AC02 existed
    assert again.assigned == ()  # nothing new to mint
    assert again.registry == {"FR-01.11": 3}  # high-water mark unmoved

    # A genuinely new criterion added afterwards must NOT reuse AC02.
    lines.append("- (E) A fresh criterion added after the deletion.")
    with_new = "\n".join(lines)
    third = ac_identity.mint(with_new, again.registry)
    assert third.assigned == (("FR-01.11", "AC04"),)


def test_seeding_from_a_document_ahead_of_a_stale_registry():
    """If the registry snapshot lagged behind hand-edited markers, mint()
    seeds itself from the document rather than clashing."""
    already_marked = (
        "### FR-05.01 — Title\n\n"
        "- (E) [AC05] Given a thing, when it happens, then it holds.\n"
        "- (E) Given a second thing, when it happens, then it holds too.\n"
    )
    result = ac_identity.mint(already_marked, registry={})
    assert result.assigned == (("FR-05.01", "AC06"),)
    assert result.registry == {"FR-05.01": 6}


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


# ---------------------------------------------------------------------------
# read() — the reader half, built on lib.fr_criteria (R0).
# ---------------------------------------------------------------------------

def test_read_returns_minted_ids_paired_with_their_text():
    minted = ac_identity.mint(FRESH_FR).content
    criteria = ac_identity.read(minted, "FR-01.11")
    assert [ac_id for ac_id, _ in criteria] == ["AC01", "AC02", "AC03"]
    ac01_id, ac01_text = criteria[0]
    assert ac01_id == "AC01"
    assert ac01_text.startswith("Given a change described in ordinary words")


def test_read_reports_none_for_a_not_yet_minted_criterion():
    criteria = ac_identity.read(FRESH_FR, "FR-01.11")
    assert [ac_id for ac_id, _ in criteria] == [None, None, None]


def test_read_all_covers_every_fr_in_document_order():
    minted = ac_identity.mint(TWO_FRS).content
    by_fr = ac_identity.read_all(minted)
    assert list(by_fr.keys()) == ["FR-01.01", "FR-01.02"]
    assert by_fr["FR-01.01"][0][0] == "AC01"
    assert by_fr["FR-01.02"][0][0] == "AC01"


def test_read_agrees_with_fr_criteria_on_continuation_line_joining():
    """The wrapped second line of a criterion joins onto the first -- proof
    that read() actually delegates to fr_criteria rather than reimplementing
    (and silently diverging from) its continuation-line rule."""
    minted = ac_identity.mint(FRESH_FR).content
    _, text = ac_identity.read(minted, "FR-01.11")[1]
    assert text == (
        "Given a feature or a change, when it is classified, then it records "
        "whether it adds, modifies, removes or leaves the requirements untouched."
    )


# Marker-validation edge cases (malformed/duplicate markers, registry gaps)
# and boundary shapes (blank lines, heading rank) live in
# ``test_ac_identity_markers.py`` -- split there purely to keep both files
# under the 300-LOC bloat-baseline threshold.
