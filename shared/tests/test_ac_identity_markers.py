"""Marker-validation + boundary-shape pins for ``lib.ac_identity`` /
``lib._ac_markers`` (external plan review, 2026-09-06).

Split out of ``test_ac_identity.py`` (which covers fresh mint/idempotency/
read) purely to keep both files under the 300-LOC bloat-baseline threshold —
same content that would otherwise sit in one file, not a different subject.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))

from lib import ac_identity  # noqa: E402


# ---------------------------------------------------------------------------
# Marker validation — HIGH + MEDIUM findings.
# ---------------------------------------------------------------------------

def test_a_registry_high_water_mark_ahead_of_the_document_is_preserved_not_reused():
    """The registry may legitimately know about a number no marker in the
    CURRENT document carries (a deleted criterion, or a document/registry
    write interrupted between the two) -- mint() must not treat the gap as
    free."""
    fresh_fr = (
        "### FR-01.11 — /shipwright-iterate\n\n"
        "- (E) Given a change described in ordinary words, when it is picked up,\n"
        "  then its kind and size are detected.\n"
    )
    result = ac_identity.mint(fresh_fr, registry={"FR-01.11": 10})
    assert result.assigned == (("FR-01.11", "AC11"),)
    assert result.registry == {"FR-01.11": 11}


def test_a_non_canonical_digit_string_is_rejected_not_silently_accepted():
    doc = "### FR-06.01 — Title\n\n- (E) [AC7] Given a thing, when it happens, then it holds.\n"
    for fn in (lambda: ac_identity.mint(doc), lambda: ac_identity.read(doc, "FR-06.01")):
        try:
            fn()
            raise AssertionError("expected MalformedAcMarkerError")
        except ac_identity.MalformedAcMarkerError:
            pass


def test_a_near_miss_marker_is_rejected_not_read_as_ordinary_prose():
    """External code review, 2026-09-06 round 2: `[AC 1]` and `[ac01]` fall
    outside `AC_MARKER_RE` entirely -- without the near-miss probe, mint()
    would treat the bullet as unmarked (stacking a second, real marker in
    front on every rerun) and read() would report it as never-minted,
    forever. Both directions violate "fails loudly, never silently"."""
    for near_miss in ("[AC 1] Given a thing, when it happens, then it holds.",
                       "[ac01] Given a thing, when it happens, then it holds."):
        doc = f"### FR-06.07 — Title\n\n- (E) {near_miss}\n"
        for fn in (lambda d=doc: ac_identity.mint(d), lambda d=doc: ac_identity.read(d, "FR-06.07")):
            try:
                fn()
                raise AssertionError(f"expected MalformedAcMarkerError for {near_miss!r}")
            except ac_identity.MalformedAcMarkerError:
                pass


def test_a_negative_registry_value_is_rejected_not_used_to_mint_ac00():
    """External code review, 2026-09-06 round 2: a hand-edited registry of
    `-1` would otherwise flow into `+ 1` and mint `[AC00]` -- a marker
    parse_marker itself rejects on the very next run."""
    doc = "### FR-06.08 — Title\n\n- (E) Given a thing, when it happens, then it holds.\n"
    try:
        ac_identity.mint(doc, registry={"FR-06.08": -1})
        raise AssertionError("expected InvalidRegistryError")
    except ac_identity.InvalidRegistryError:
        pass


def test_two_markers_stacked_on_one_criterion_is_rejected():
    doc = (
        "### FR-06.02 — Title\n\n"
        "- (E) [AC01] [AC02] Given a thing, when it happens, then it holds.\n"
    )
    try:
        ac_identity.mint(doc)
        raise AssertionError("expected MalformedAcMarkerError")
    except ac_identity.MalformedAcMarkerError:
        pass


def test_two_criteria_sharing_one_ac_number_is_rejected():
    doc = (
        "### FR-06.03 — Title\n\n"
        "- (E) [AC01] Given a first thing, when it happens, then it holds.\n"
        "- (E) [AC01] Given a second thing, when it happens, then it holds too.\n"
    )
    try:
        ac_identity.mint(doc)
        raise AssertionError("expected DuplicateAcIdError")
    except ac_identity.DuplicateAcIdError:
        pass
    try:
        ac_identity.read(doc, "FR-06.03")
        raise AssertionError("expected DuplicateAcIdError")
    except ac_identity.DuplicateAcIdError:
        pass


def test_a_marker_inside_a_continuation_line_is_ordinary_text_not_an_id():
    """A literal ``[AC03]``-shaped substring on a WRAPPED second line (not
    the bullet's opening line) is never parsed as this criterion's marker --
    only the opening line is inspected."""
    doc = (
        "### FR-06.04 — Title\n\n"
        "- (E) Given a thing that mentions [AC03] in its own prose,\n"
        "  when it happens, then it holds.\n"
    )
    result = ac_identity.mint(doc)
    assert result.assigned == (("FR-06.04", "AC01"),)
    _, text = ac_identity.read(result.content, "FR-06.04")[0]
    assert "[AC03] in its own prose" in text


def test_ac00_is_rejected_since_mint_never_assigns_it():
    doc = "### FR-06.05 — Title\n\n- (E) [AC00] Given a thing, when it happens, then it holds.\n"
    for fn in (lambda: ac_identity.mint(doc), lambda: ac_identity.read(doc, "FR-06.05")):
        try:
            fn()
            raise AssertionError("expected MalformedAcMarkerError")
        except ac_identity.MalformedAcMarkerError:
            pass


def test_mint_and_read_agree_on_a_duplicate_split_across_a_placeholder():
    """CHECKED, not reproduced (external code review, 2026-09-06, GLM low #3
    theorised an asymmetry here; empirically it does not materialise). Once
    the `[ACnn]` marker is prepended to a placeholder bullet, the combined
    text (`"[AC01] TBD"` -> stripped to `ac01tbd`) no longer collapses to
    `fr_criteria`'s bare-placeholder token set, so `read()` does NOT drop the
    bullet either -- both `mint()` and `read()` see the duplicate and raise
    `DuplicateAcIdError`, exactly as they must for "never renumbered, never
    reused" to hold even when a placeholder is involved."""
    doc = (
        "### FR-06.06 — Title\n\n"
        "- [AC01] TBD\n"
        "- (E) [AC01] Given a real thing, when it happens, then it holds.\n"
    )
    try:
        ac_identity.mint(doc)
        raise AssertionError("expected DuplicateAcIdError")
    except ac_identity.DuplicateAcIdError:
        pass
    try:
        ac_identity.read(doc, "FR-06.06")
        raise AssertionError("expected DuplicateAcIdError")
    except ac_identity.DuplicateAcIdError:
        pass


def test_a_legacy_bold_anchor_block_is_out_of_scope_for_read_too():
    """`read()`/`read_all()` must agree with `mint()`'s own scope: neither
    scans the legacy bold-anchor form `fr_criteria` still tolerates for older
    documents (external code review, 2026-09-06, openai medium)."""
    doc = "**FR-08.01: Legacy Title**\n- (E) belongs to the legacy form, not the shipped shape.\n"
    result = ac_identity.mint(doc)
    assert result.assigned == ()  # mint() never touches a bold-anchored block
    assert ac_identity.read(doc, "FR-08.01") == []
    assert ac_identity.read_all(doc) == {}


def test_an_indented_sub_bullet_is_minted_and_read_as_its_own_criterion():
    """A nested/indented sub-bullet still opens its own bullet line (per
    `_ac_blocks.BULLET_RE`, which allows leading whitespace) -- proof mint()
    and read() AGREE on this shape, since `fr_criteria`'s own bullet
    detection runs the SAME check before treating a line as a continuation."""
    doc = "### FR-08.02 — Title\n\n- (E) Parent criterion.\n  - (E) Nested sub-bullet.\n"
    result = ac_identity.mint(doc)
    assert result.assigned == (("FR-08.02", "AC01"), ("FR-08.02", "AC02"))
    criteria = ac_identity.read(result.content, "FR-08.02")
    assert [ac_id for ac_id, _ in criteria] == ["AC01", "AC02"]


# ---------------------------------------------------------------------------
# Boundary shapes — LOW #7. Each fixture is mint()ed THEN read() back
# (external code review, 2026-09-06, GLM medium): the golden corpus must
# pin the READER on these shapes too, not just the minter.
# ---------------------------------------------------------------------------

def test_a_blank_line_between_two_bullets_does_not_break_bullet_detection():
    doc = (
        "### FR-07.01 — Title\n\n"
        "- (E) First criterion.\n\n"
        "- (E) Second criterion.\n"
    )
    result = ac_identity.mint(doc)
    assert result.assigned == (("FR-07.01", "AC01"), ("FR-07.01", "AC02"))
    assert [ac_id for ac_id, _ in ac_identity.read(result.content, "FR-07.01")] == ["AC01", "AC02"]


def test_a_same_rank_non_fr_heading_ends_the_fr_block():
    doc = (
        "## FR-07.02 — Title\n\n"
        "- (E) real criterion.\n\n"
        "## Constraints\n\n"
        "- (E) not FR-07.02's.\n"
    )
    result = ac_identity.mint(doc)
    assert result.assigned == (("FR-07.02", "AC01"),)
    assert "[AC01] real criterion" in result.content
    assert "not FR-07.02's" in result.content  # untouched, never minted
    criteria = ac_identity.read(result.content, "FR-07.02")
    assert criteria == [("AC01", "real criterion.")]


def test_a_deeper_heading_ends_the_leading_bullet_run_though_not_the_block():
    """A REAL divergence, surfaced by round-tripping this fixture (external
    code review, 2026-09-06, GLM medium: "if fr_criteria's termination rule
    differs in any way ... mint() would assign an id to a bullet read() drops
    -- and no test would fail"). The deeper `#### Notes` heading does NOT end
    FR-07.03's block (still true -- only a same-or-higher-rank heading would),
    but it DOES sit before the bullet as the block's first non-blank line, so
    it disqualifies read()'s (`fr_criteria.block_criteria(strict=True)`)
    leading-bullet-run gate -- and mint() now applies that SAME gate, so
    neither mints nor reads a criterion here. Not the shipped shape anyway
    (every real spec this repo ships has no heading between an FR heading and
    its bullets, per `fr_criteria`'s own module docstring); the fix keeps
    mint() from ever stamping an id read() can never see, rather than
    special-casing this one shape."""
    doc = "## FR-07.03 — Title\n\n#### Notes\n\n- (E) still inside FR-07.03.\n"
    result = ac_identity.mint(doc)
    assert result.assigned == ()
    assert "[AC01]" not in result.content
    assert ac_identity.read(result.content, "FR-07.03") == []


def test_a_second_fr_heading_starts_a_new_block_immediately():
    doc = (
        "### FR-07.04 — First\n\n- (E) belongs to 07.04.\n"
        "### FR-07.05 — Second\n\n- (E) belongs to 07.05.\n"
    )
    result = ac_identity.mint(doc)
    assert result.assigned == (("FR-07.04", "AC01"), ("FR-07.05", "AC01"))
    by_fr = ac_identity.read_all(result.content)
    assert by_fr["FR-07.04"][0][0] == "AC01"
    assert by_fr["FR-07.05"][0][0] == "AC01"
