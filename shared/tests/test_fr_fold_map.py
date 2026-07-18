"""Unit cases for the shared ``FR-Fold-Map`` parser + resolver (fold-map resolution).

The fold-map lets a spec fold a fine-grained FR into a broader capability FR while
keeping every historical reference resolvable. These cases pin the SAFETY property the
whole feature rests on: fold resolution is a **fallback**, never an override — it can
only rescue a tag that would otherwise orphan, and every ambiguous / broken / dead edge
fails CLOSED (tag stays an orphan) with a recorded defect rather than a silent guess.

@FR-01.10
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts" / "lib"))

from fr_fold_map import (  # noqa: E402
    FOLD_DEFECT_KINDS,
    audit_fold_map,
    merge_fold_maps,
    parse_fold_map,
    resolve_fold,
)


def _spec(rows: str, *, heading: str = "## FR-Fold-Map") -> str:
    return (
        "# Spec\n\n## Functional Requirements\n\n"
        "| FR | Description | Priority | Layers |\n"
        "|----|----|----|----|\n"
        "| FR-01.28 | Embedded terminal | Must | unit |\n\n"
        f"{heading}\n\n"
        "| Folded ID | → Survivor | Reason | Was |\n"
        "|---|---|---|---|\n"
        f"{rows}\n\n"
        "## How to read\n\nprose\n"
    )


# --------------------------------------------------------------------------
# Parsing
# --------------------------------------------------------------------------


def test_parses_backticked_edges_as_shipped_by_webui():
    """The real-world shape (webui #287): ids wrapped in backticks."""
    fm = parse_fold_map(_spec("| `FR-01.44` | `FR-01.28` | delta | Terminal look |"))
    assert fm.edges == {"FR-01.44": "FR-01.28"}
    assert fm.defects == ()


def test_parses_bare_and_arrow_prefixed_cells():
    """Unbackticked ids and an arrow left in the survivor cell both parse."""
    fm = parse_fold_map(_spec(
        "| FR-01.44 | FR-01.28 | delta | a |\n"
        "| `FR-01.45` | → `FR-01.28` | delta | b |\n"
        "| FR-01.46 | -> FR-01.28 | delta | c |"
    ))
    assert fm.edges == {
        "FR-01.44": "FR-01.28", "FR-01.45": "FR-01.28", "FR-01.46": "FR-01.28",
    }


def test_heading_variants_are_recognised():
    for heading in ("## FR-Fold-Map", "### FR Fold Map", "## fr-fold-map", "## FR-Fold-Map "):
        fm = parse_fold_map(_spec("| `FR-01.44` | `FR-01.28` | d | x |", heading=heading))
        assert fm.edges == {"FR-01.44": "FR-01.28"}, heading


def test_section_ends_at_next_sibling_heading():
    """Rows after the section's closing heading are NOT fold edges."""
    text = _spec("| `FR-01.44` | `FR-01.28` | delta | a |") + (
        "\n| FR-09.01 | FR-09.02 | not-a-fold | z |\n"
    )
    assert parse_fold_map(text).edges == {"FR-01.44": "FR-01.28"}


def test_no_fold_map_section_yields_empty_map():
    fm = parse_fold_map("# Spec\n\n| FR-01.01 | x | Must | unit |\n")
    assert fm.edges == {} and fm.defects == ()


def test_header_and_separator_rows_are_not_defects():
    fm = parse_fold_map(_spec("| `FR-01.44` | `FR-01.28` | delta | a |"))
    assert not [d for d in fm.defects if d.kind == "unparsable_row"]


def test_unparsable_row_is_recorded_not_swallowed():
    fm = parse_fold_map(_spec("| `FR-1.4` | `FR-01.28` | delta | typo |"))
    assert fm.edges == {}
    assert [d.kind for d in fm.defects] == ["unparsable_row"]


def test_self_fold_is_dropped_and_recorded():
    fm = parse_fold_map(_spec("| `FR-01.44` | `FR-01.44` | delta | loop |"))
    assert fm.edges == {}
    assert [d.kind for d in fm.defects] == ["self_fold"]


# --------------------------------------------------------------------------
# Merge across specs
# --------------------------------------------------------------------------


def test_merge_unions_disjoint_maps():
    a = parse_fold_map(_spec("| `FR-01.44` | `FR-01.28` | d | a |"))
    b = parse_fold_map(_spec("| `FR-02.10` | `FR-02.01` | d | b |"))
    merged = merge_fold_maps([a, b])
    assert merged.edges == {"FR-01.44": "FR-01.28", "FR-02.10": "FR-02.01"}


def test_conflicting_survivors_drop_the_edge_fail_closed():
    """Two specs folding the same id to DIFFERENT survivors is ambiguous — never guess."""
    a = parse_fold_map(_spec("| `FR-01.44` | `FR-01.28` | d | a |"))
    b = parse_fold_map(_spec("| `FR-01.44` | `FR-01.99` | d | b |"))
    merged = merge_fold_maps([a, b])
    assert "FR-01.44" not in merged.edges
    assert [d.kind for d in merged.defects] == ["conflicting_survivor"]


def test_merge_keeps_identical_duplicate_edge_without_defect():
    a = parse_fold_map(_spec("| `FR-01.44` | `FR-01.28` | d | a |"))
    b = parse_fold_map(_spec("| `FR-01.44` | `FR-01.28` | d | a |"))
    merged = merge_fold_maps([a, b])
    assert merged.edges == {"FR-01.44": "FR-01.28"} and merged.defects == ()


# --------------------------------------------------------------------------
# Resolution — the safety property
# --------------------------------------------------------------------------


def _active(*ids):
    live = set(ids)
    return lambda fr: fr in live


def test_active_id_resolves_to_itself_without_consulting_the_map():
    """Rule 1: a live FR is NEVER redirected by a fold-map (no override)."""
    fm = merge_fold_maps([parse_fold_map(_spec("| `FR-01.28` | `FR-01.99` | d | a |"))])
    res = resolve_fold(fm, "FR-01.28", is_active=_active("FR-01.28", "FR-01.99"))
    assert res.survivor == "FR-01.28"
    assert res.via == ()
    assert res.folded is False


def test_folded_id_resolves_to_active_survivor():
    fm = parse_fold_map(_spec("| `FR-01.44` | `FR-01.28` | d | a |"))
    res = resolve_fold(fm, "FR-01.44", is_active=_active("FR-01.28"))
    assert res.survivor == "FR-01.28"
    assert res.folded is True
    assert res.via == ("FR-01.44", "FR-01.28")


def test_transitive_chain_resolves_to_the_final_active_survivor():
    fm = parse_fold_map(_spec(
        "| `FR-01.44` | `FR-01.45` | d | a |\n"
        "| `FR-01.45` | `FR-01.28` | d | b |"
    ))
    res = resolve_fold(fm, "FR-01.44", is_active=_active("FR-01.28"))
    assert res.survivor == "FR-01.28"
    assert res.via == ("FR-01.44", "FR-01.45", "FR-01.28")


def test_cycle_fails_closed_and_terminates():
    """A→B→A must not hang and must NOT resolve."""
    fm = parse_fold_map(_spec(
        "| `FR-01.44` | `FR-01.45` | d | a |\n"
        "| `FR-01.45` | `FR-01.44` | d | b |"
    ))
    res = resolve_fold(fm, "FR-01.44", is_active=_active("FR-01.28"))
    assert res.survivor is None
    assert res.reason == "cycle"


def test_dangling_survivor_fails_closed():
    """Survivor is in no FR table at all → the tag still orphans."""
    fm = parse_fold_map(_spec("| `FR-01.44` | `FR-01.77` | d | a |"))
    res = resolve_fold(fm, "FR-01.44", is_active=_active("FR-01.28"))
    assert res.survivor is None
    assert res.reason == "unresolved"


def test_untracked_id_is_not_folded():
    fm = parse_fold_map(_spec("| `FR-01.44` | `FR-01.28` | d | a |"))
    res = resolve_fold(fm, "FR-07.07", is_active=_active("FR-01.28"))
    assert res.survivor is None and res.folded is False


def test_depth_cap_terminates_a_long_chain():
    rows = "\n".join(
        f"| `FR-05.{i:02d}` | `FR-05.{i + 1:02d}` | d | x |" for i in range(1, 60)
    )
    fm = parse_fold_map(_spec(rows))
    res = resolve_fold(fm, "FR-05.01", is_active=_active("FR-05.59"))
    assert res.survivor is None
    assert res.reason == "depth_exceeded"


# --------------------------------------------------------------------------
# Table-dependent audit
# --------------------------------------------------------------------------


def test_audit_flags_folded_id_that_is_still_an_active_row():
    fm = parse_fold_map(_spec("| `FR-01.44` | `FR-01.28` | d | a |"))
    defects = audit_fold_map(fm, active_ids={"FR-01.28", "FR-01.44"}, removed_ids=set())
    assert [d.kind for d in defects] == ["folded_id_still_active"]


def test_audit_flags_dangling_survivor():
    fm = parse_fold_map(_spec("| `FR-01.44` | `FR-01.77` | d | a |"))
    defects = audit_fold_map(fm, active_ids={"FR-01.28"}, removed_ids=set())
    assert [d.kind for d in defects] == ["dangling_survivor"]


def test_audit_flags_survivor_that_is_removed():
    """A fold must never credit coverage to a retired requirement."""
    fm = parse_fold_map(_spec("| `FR-01.44` | `FR-01.28` | d | a |"))
    defects = audit_fold_map(fm, active_ids=set(), removed_ids={"FR-01.28"})
    assert [d.kind for d in defects] == ["removed_survivor"]


def test_audit_is_clean_for_a_healthy_map():
    fm = parse_fold_map(_spec("| `FR-01.44` | `FR-01.28` | d | a |"))
    assert audit_fold_map(fm, active_ids={"FR-01.28"}, removed_ids=set()) == ()


def test_every_emitted_defect_kind_is_in_the_closed_vocabulary():
    """Drift guard: a new defect kind must be declared, so consumers can render it."""
    fm = parse_fold_map(_spec(
        "| `FR-01.44` | `FR-01.44` | d | self |\n"
        "| `FR-9.9`   | `FR-01.28` | d | bad  |\n"
        "| `FR-01.45` | `FR-01.77` | d | dang |"
    ))
    defects = list(fm.defects) + list(
        audit_fold_map(fm, active_ids={"FR-01.28"}, removed_ids=set()))
    assert defects
    for d in defects:
        assert d.kind in FOLD_DEFECT_KINDS, d.kind


@pytest.mark.parametrize("bad", ["", "   ", "not a spec", "| | |", "## FR-Fold-Map\n"])
def test_parser_never_raises_on_degenerate_input(bad):
    fm = parse_fold_map(bad)
    assert fm.edges == {}
