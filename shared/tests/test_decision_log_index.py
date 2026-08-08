"""Renderer rules for ``decision_log_index.md`` — parsing and rendering only.

The call sites that drive it (write_decision_log.py, aggregate_decisions.py)
and the drift guard live in ``test_decision_log_index_producers.py``. Writing
mechanics (atomicity, locking, LF-exactness) live in
``test_decision_log_index_writing.py``. This file mirrors
``test_adr_index.py``'s split.
"""

from __future__ import annotations

from lib.decision_log_index import (
    _entries,
    _slugify_heading,
    _supersession_map,
    render_decision_log_index,
)


def test_no_entries_renders_the_empty_state():
    out = render_decision_log_index("# Decision Log\n\nnothing here\n")
    assert "No decisions yet" in out


def test_a_single_entry_is_listed_with_its_own_title():
    text = "### ADR-009: Adopt this repository into the Shipwright SDLC\n- **Status**: accepted\n"
    out = render_decision_log_index(text)
    assert "- [ADR-009 — Adopt this repository into the Shipwright SDLC]" in out
    assert "(decision_log.md#adr-009-adopt-this-repository-into-the-shipwright-sdlc)" in out


def test_a_bare_heading_with_no_title_still_renders():
    out = render_decision_log_index("### ADR-042\n- **Status**: accepted\n")
    assert "- [ADR-042](decision_log.md#adr-042)" in out


def test_entries_keep_file_order_not_sorted():
    text = "### ADR-020: Second\n\n### ADR-005: First\n"
    out = render_decision_log_index(text)
    assert out.index("ADR-020") < out.index("ADR-005")


def test_headings_inside_a_fenced_code_block_are_ignored():
    text = "### ADR-001: Real\n\n```\n### ADR-999: Not a real entry\n```\n"
    out = render_decision_log_index(text)
    assert "ADR-001" in out
    assert "ADR-999" not in out


def test_a_tilde_fence_is_also_respected():
    text = "### ADR-001: Real\n\n~~~\n### ADR-999: Not a real entry\n~~~\n"
    out = render_decision_log_index(text)
    assert "ADR-999" not in out


def test_supersedes_marker_annotates_the_superseded_entry():
    text = (
        "### ADR-042: Old rule\n\n"
        "### ADR-307: New rule (supersedes ADR-042 old behaviour)\n"
    )
    out = render_decision_log_index(text)
    lines = out.splitlines()
    old_row = next(ln for ln in lines if ln.startswith("- [ADR-042"))
    new_row = next(ln for ln in lines if ln.startswith("- [ADR-307"))
    assert "superseded by ADR-307" in old_row
    assert "superseded by" not in new_row


def test_supersedes_is_case_insensitive():
    text = (
        "### ADR-001: Old\n\n"
        "### ADR-002: New (SUPERSEDES ADR-001)\n"
    )
    out = render_decision_log_index(text)
    old_row = next(ln for ln in out.splitlines() if ln.startswith("- [ADR-001"))
    assert "superseded by ADR-002" in old_row


def test_bracket_in_title_is_escaped_so_the_link_label_is_not_truncated():
    text = "### ADR-050: Use [square] brackets\n"
    out = render_decision_log_index(text)
    assert r"\[square\]" in out


def test_render_is_lf_only():
    text = "### ADR-001: X\n"
    out = render_decision_log_index(text)
    assert "\r" not in out


def test_entries_helper_returns_num_and_title_in_order():
    text = "### ADR-001: A\n\n### ADR-002: B\n"
    assert _entries(text) == [("ADR", "001", "A"), ("ADR", "002", "B")]


def test_supersession_map_ignores_entries_without_the_marker():
    entries = [("ADR", "001", "Plain title"), ("ADR", "002", "Another (unrelated parenthetical)")]
    assert _supersession_map(entries) == {}


def test_design_dr_entries_are_indexed_alongside_adr_entries():
    """shipwright-design writes `### DR-NNN: Title` into the SAME decision_log.md
    (a second, independently-numbered entry class) — an index that claims to
    list every decision must not silently drop them."""
    text = "### ADR-001: Backend choice\n\n### DR-001: Button color\n"
    out = render_decision_log_index(text)
    assert "- [DR-001 — Button color](decision_log.md#dr-001-button-color)" in out
    assert "- [ADR-001 — Backend choice]" in out


def test_dr_entries_are_never_annotated_as_superseded():
    """The supersedes vocabulary is ADR-only; a DR-NNN and an ADR-NNN sharing
    digits must not collide through the shared numeric key."""
    text = "### DR-042: A design choice\n\n### ADR-307: New rule (supersedes ADR-042)\n"
    out = render_decision_log_index(text)
    dr_row = next(ln for ln in out.splitlines() if ln.startswith("- [DR-042"))
    assert "superseded by" not in dr_row


def test_supersedes_matches_an_unpadded_reference_to_a_zero_padded_heading():
    """A hand-authored ``(supersedes ADR-42)`` must still hit heading ``042`` —
    the marker is typed by a human, not generated, so it is the likeliest typo."""
    text = "### ADR-042: Old rule\n\n### ADR-307: New rule (supersedes ADR-42)\n"
    out = render_decision_log_index(text)
    old_row = next(ln for ln in out.splitlines() if ln.startswith("- [ADR-042"))
    assert "superseded by ADR-307" in old_row


def test_supersedes_annotates_every_target_in_a_multi_target_marker():
    text = (
        "### ADR-042: First old rule\n\n"
        "### ADR-100: Second old rule\n\n"
        "### ADR-310: New rule (supersedes ADR-042 and ADR-100)\n"
    )
    out = render_decision_log_index(text)
    lines = out.splitlines()
    row_042 = next(ln for ln in lines if ln.startswith("- [ADR-042"))
    row_100 = next(ln for ln in lines if ln.startswith("- [ADR-100"))
    assert "superseded by ADR-310" in row_042
    assert "superseded by ADR-310" in row_100


def test_an_earlier_entrys_marker_cannot_supersede_a_later_entry():
    """A marker only counts from a LATER entry — an out-of-order/malformed
    earlier entry claiming to supersede a later ADR must not flip the
    direction (the later entry is the newer decision, not the superseded one)."""
    text = (
        "### ADR-001: Old, mistakenly claims to supersede a later entry (supersedes ADR-002)\n\n"
        "### ADR-002: Actually the later, real entry\n"
    )
    out = render_decision_log_index(text)
    row_002 = next(ln for ln in out.splitlines() if ln.startswith("- [ADR-002"))
    assert "superseded by" not in row_002


def test_supersedes_does_not_over_derive_from_an_unrelated_adr_mention():
    """`(supersedes ADR-042, see ADR-100)` must annotate only ADR-042 — the
    trailing free text can reference another ADR without becoming a second
    supersession target."""
    text = (
        "### ADR-042: Old rule\n\n"
        "### ADR-100: Unrelated, merely mentioned\n\n"
        "### ADR-307: New rule (supersedes ADR-042, see ADR-100)\n"
    )
    out = render_decision_log_index(text)
    row_042 = next(ln for ln in out.splitlines() if ln.startswith("- [ADR-042"))
    row_100 = next(ln for ln in out.splitlines() if ln.startswith("- [ADR-100"))
    assert "superseded by ADR-307" in row_042
    assert "superseded by" not in row_100


def test_supersedes_marker_need_not_be_the_last_thing_in_the_title():
    text = (
        "### ADR-042: Old rule\n\n"
        "### ADR-310: New rule (supersedes ADR-042) — follow-up\n"
    )
    out = render_decision_log_index(text)
    old_row = next(ln for ln in out.splitlines() if ln.startswith("- [ADR-042"))
    assert "superseded by ADR-310" in old_row


def test_slugify_matches_github_heading_anchor_shape():
    assert _slugify_heading("ADR-009: Adopt this repository") == "adr-009-adopt-this-repository"
