"""Hardening cases for the shared FR-Fold-Map contract — every one traces to a finding
from the external plan review (GPT-5.4 + Gemini 3.1 Pro) of this iterate.

Split from ``test_fr_fold_map.py`` to keep each file under the 300-LOC cap. Where that
review disagreed with the design, the case below pins the decision that was actually
taken, so the reasoning is testable rather than only argued in a PR thread.

@FR-01.10
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts" / "lib"))

from _fr_fold_map_parse import (  # noqa: E402
    MAX_RAW_LEN,
    fold_map_line_numbers,
    fold_map_section_spans,
    has_fold_map_section,
)
from fr_fold_map import (  # noqa: E402
    audit_fold_map,
    merge_fold_maps,
    parse_fold_map,
    resolve_fold,
)

_FR_TABLE = (
    "## Functional Requirements\n\n"
    "| FR | Description | Priority | Layers |\n"
    "|----|----|----|----|\n"
    "| FR-01.28 | Embedded terminal | Must | unit |\n\n"
)


def _active(*ids):
    live = set(ids)
    return lambda fr: fr in live


# --------------------------------------------------------------------------
# GPT #4 — terminal-based resolution through inactive intermediates
# --------------------------------------------------------------------------


def test_chain_resolves_through_a_REMOVED_intermediate_to_an_active_terminal():
    """A→B→C with B removed and C active resolves to C.

    The rule is terminal-based, not per-hop: an intermediate is just a waypoint. Pinned
    because a per-hop reading ("stop at B, B is removed, give up") is an equally natural
    implementation and would silently diverge between collector and backfill.
    """
    fm = parse_fold_map(
        f"{_FR_TABLE}## FR-Fold-Map\n\n"
        "| `FR-01.44` | `FR-01.45` | delta | a |\n"
        "| `FR-01.45` | `FR-01.28` | delta | b |\n"
    )
    res = resolve_fold(fm, "FR-01.44", is_active=_active("FR-01.28"))
    assert res.survivor == "FR-01.28"
    assert res.via == ("FR-01.44", "FR-01.45", "FR-01.28")


def test_chain_whose_terminal_is_removed_fails_closed():
    """The terminal decides — a chain ending at a retired FR rescues nothing."""
    fm = parse_fold_map(
        f"{_FR_TABLE}## FR-Fold-Map\n\n"
        "| `FR-01.44` | `FR-01.45` | delta | a |\n"
        "| `FR-01.45` | `FR-01.99` | delta | b |\n"
    )
    res = resolve_fold(fm, "FR-01.44", is_active=_active("FR-01.28"))
    assert res.survivor is None
    assert res.reason == "unresolved"


# --------------------------------------------------------------------------
# GPT #9 — an id that is BOTH folded and still active
# --------------------------------------------------------------------------


def test_active_folded_id_keeps_its_own_coverage_and_ignores_its_fold_entry():
    """Rule 1 in its sharpest form: the fold entry for a live id is inert.

    A tag on FR-01.44 must credit FR-01.44 (which is still active and still owes its own
    coverage), NOT the survivor — otherwise the live requirement silently goes uncovered
    while its tests are counted elsewhere.
    """
    fm = parse_fold_map(
        f"{_FR_TABLE}## FR-Fold-Map\n\n| `FR-01.44` | `FR-01.28` | delta | a |\n")
    res = resolve_fold(fm, "FR-01.44", is_active=_active("FR-01.44", "FR-01.28"))
    assert res.survivor == "FR-01.44"
    assert res.folded is False
    # ...and the contradiction is still surfaced as hygiene.
    kinds = [d.kind for d in audit_fold_map(
        fm, active_ids={"FR-01.44", "FR-01.28"}, removed_ids=set())]
    assert kinds == ["folded_id_still_active"]


# --------------------------------------------------------------------------
# Gemini #3 — duplicate rows WITHIN one spec
# --------------------------------------------------------------------------


def test_intra_spec_duplicate_conflicting_rows_drop_the_edge():
    """A copy-paste / merge-conflict artifact must not silently last-write-wins."""
    fm = parse_fold_map(
        f"{_FR_TABLE}## FR-Fold-Map\n\n"
        "| `FR-01.44` | `FR-01.28` | delta | a |\n"
        "| `FR-01.44` | `FR-01.99` | delta | dup |\n"
    )
    assert "FR-01.44" not in fm.edges
    assert [d.kind for d in fm.defects] == ["conflicting_survivor"]


def test_intra_spec_duplicate_identical_rows_are_one_edge_no_defect():
    fm = parse_fold_map(
        f"{_FR_TABLE}## FR-Fold-Map\n\n"
        "| `FR-01.44` | `FR-01.28` | delta | a |\n"
        "| `FR-01.44` | `FR-01.28` | delta | a |\n"
    )
    assert fm.edges == {"FR-01.44": "FR-01.28"}
    assert fm.defects == ()


# --------------------------------------------------------------------------
# GPT #5 — cycle is a recorded defect, emitted once per map
# --------------------------------------------------------------------------


def test_cycle_is_recorded_as_a_defect_exactly_once_not_once_per_member():
    """One broken loop = one diagnostic, however many tags reference it."""
    fm = parse_fold_map(
        f"{_FR_TABLE}## FR-Fold-Map\n\n"
        "| `FR-01.44` | `FR-01.45` | delta | a |\n"
        "| `FR-01.45` | `FR-01.46` | delta | b |\n"
        "| `FR-01.46` | `FR-01.44` | delta | c |\n"
    )
    cycles = [d for d in audit_fold_map(fm, active_ids={"FR-01.28"}, removed_ids=set())
              if d.kind == "cycle"]
    assert len(cycles) == 1
    assert cycles[0].folded == "FR-01.44"          # named by smallest member — stable
    assert "FR-01.45" in cycles[0].raw


def test_a_cycle_does_not_also_spawn_dangling_survivor_noise():
    """One root cause, one actionable defect.

    Inside a loop no member is an active FR, so a naive audit reports the cycle PLUS a
    ``dangling_survivor`` for every edge in it — burying the one finding that explains
    the rest. Regression: this returned 3 defects for a single 2-edge loop.
    """
    fm = parse_fold_map(
        f"{_FR_TABLE}## FR-Fold-Map\n\n"
        "| `FR-01.44` | `FR-01.45` | d | a |\n"
        "| `FR-01.45` | `FR-01.44` | d | b |\n"
    )
    kinds = [d.kind for d in audit_fold_map(
        fm, active_ids={"FR-01.28"}, removed_ids=set())]
    assert kinds == ["cycle"]


def test_edges_outside_a_cycle_are_still_audited_normally():
    """Suppression is scoped to looped ids — an unrelated bad edge must still report."""
    fm = parse_fold_map(
        f"{_FR_TABLE}## FR-Fold-Map\n\n"
        "| `FR-01.44` | `FR-01.45` | d | a |\n"
        "| `FR-01.45` | `FR-01.44` | d | b |\n"
        "| `FR-02.10` | `FR-02.99` | d | unrelated |\n"
    )
    kinds = sorted(d.kind for d in audit_fold_map(
        fm, active_ids={"FR-01.28"}, removed_ids=set()))
    assert kinds == ["cycle", "dangling_survivor"]


def test_two_independent_cycles_yield_two_defects():
    fm = parse_fold_map(
        f"{_FR_TABLE}## FR-Fold-Map\n\n"
        "| `FR-01.44` | `FR-01.45` | d | a |\n"
        "| `FR-01.45` | `FR-01.44` | d | b |\n"
        "| `FR-02.10` | `FR-02.11` | d | c |\n"
        "| `FR-02.11` | `FR-02.10` | d | d |\n"
    )
    cycles = [d for d in audit_fold_map(fm, active_ids=set(), removed_ids=set())
              if d.kind == "cycle"]
    assert len(cycles) == 2


# --------------------------------------------------------------------------
# Gemini #1 / GPT #7 — markdown section boundary precision
# --------------------------------------------------------------------------


def test_a_following_requirement_table_is_not_swallowed_by_the_section():
    """The exact false-positive Gemini flagged: skipping to EOF instead of to the
    next sibling heading would eat every later requirement row."""
    text = (
        "## FR-Fold-Map\n\n| `FR-01.44` | `FR-01.28` | d | a |\n\n"
        "## More Requirements\n\n| FR-09.01 | Later thing | Must | unit |\n"
    )
    spans = fold_map_section_spans(text)
    assert len(spans) == 1
    later = text.splitlines().index("| FR-09.01 | Later thing | Must | unit |")
    assert later not in fold_map_line_numbers(text)
    assert parse_fold_map(text).edges == {"FR-01.44": "FR-01.28"}


def test_a_deeper_subheading_does_not_truncate_the_section():
    text = (
        "## FR-Fold-Map\n\n### Endpoints\n\n| `FR-01.44` | `FR-01.28` | d | a |\n\n"
        "### Deltas\n\n| `FR-01.45` | `FR-01.28` | d | b |\n\n"
        "## Next\n\n| FR-09.01 | x | Must | unit |\n"
    )
    assert parse_fold_map(text).edges == {
        "FR-01.44": "FR-01.28", "FR-01.45": "FR-01.28"}


def test_repeated_fold_map_sections_are_all_parsed():
    """A parser honouring only the first section would let the rest leak into the
    FR table as live requirements."""
    text = (
        "## FR-Fold-Map\n\n| `FR-01.44` | `FR-01.28` | d | a |\n\n"
        "## Something Else\n\nprose\n\n"
        "## FR-Fold-Map\n\n| `FR-02.10` | `FR-02.01` | d | b |\n"
    )
    assert len(fold_map_section_spans(text)) == 2
    assert parse_fold_map(text).edges == {
        "FR-01.44": "FR-01.28", "FR-02.10": "FR-02.01"}


def test_section_at_end_of_file_without_a_closing_heading():
    text = "## FR-Fold-Map\n\n| `FR-01.44` | `FR-01.28` | d | a |\n"
    assert has_fold_map_section(text)
    assert parse_fold_map(text).edges == {"FR-01.44": "FR-01.28"}


def test_no_section_means_no_skipped_lines():
    assert fold_map_line_numbers(_FR_TABLE) == frozenset()
    assert not has_fold_map_section(_FR_TABLE)


# --------------------------------------------------------------------------
# Gemini #2 / GPT #10 — normalisation stance + artifact hygiene
# --------------------------------------------------------------------------


def test_lowercase_id_is_a_LOUD_defect_not_a_silent_normalisation():
    """Deliberate: the tag grammar and FR table are case-sensitive, so accepting
    `fr-01.44` here would invent a third dialect of a canonical id."""
    fm = parse_fold_map(
        f"{_FR_TABLE}## FR-Fold-Map\n\n| `fr-01.44` | `FR-01.28` | d | a |\n")
    assert fm.edges == {}
    assert [d.kind for d in fm.defects] == ["unparsable_row"]


def test_defect_carries_line_number_and_bounded_raw():
    fm = parse_fold_map(
        f"{_FR_TABLE}## FR-Fold-Map\n\n| `FR-1.4` | `FR-01.28` | d | {'x' * 400} |\n",
        spec_path=".shipwright/planning/01/spec.md")
    (defect,) = fm.defects
    assert defect.line_no > 0
    assert defect.spec_path == ".shipwright/planning/01/spec.md"
    assert len(defect.as_dict()["raw"]) <= MAX_RAW_LEN
    assert "line" in defect.as_dict()


# --------------------------------------------------------------------------
# GPT #8 — determinism
# --------------------------------------------------------------------------


def test_defects_are_deterministically_ordered_regardless_of_merge_order():
    a = parse_fold_map(f"{_FR_TABLE}## FR-Fold-Map\n\n| `FR-01.44` | `FR-01.44` | d | s |\n")
    b = parse_fold_map(f"{_FR_TABLE}## FR-Fold-Map\n\n| `FR-9.9` | `FR-01.28` | d | u |\n")
    forward = [d.sort_key() for d in merge_fold_maps([a, b]).defects]
    reverse = [d.sort_key() for d in merge_fold_maps([b, a]).defects]
    assert forward == reverse == sorted(forward)


def test_audit_output_is_sorted_and_stable():
    fm = parse_fold_map(
        f"{_FR_TABLE}## FR-Fold-Map\n\n"
        "| `FR-03.30` | `FR-03.99` | d | a |\n"
        "| `FR-02.20` | `FR-02.99` | d | b |\n"
        "| `FR-01.44` | `FR-01.99` | d | c |\n"
    )
    keys = [d.sort_key() for d in audit_fold_map(fm, active_ids=set(), removed_ids=set())]
    assert keys == sorted(keys)
