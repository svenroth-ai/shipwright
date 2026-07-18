"""Fold-map cases from this iterate's ADVERSARIAL code review (GPT-5.4 + Gemini 3.1 Pro
and the internal doubt-reviewer) — each pins a defect those passes actually found.

Split from ``test_fr_fold_map_hardening.py`` to keep both files under the 300-LOC cap.
The headline one is retirement-beats-folding: an FR under ``## Removed Requirements`` is
never fold-rescued, because otherwise removing an FR and adding one alias row in the same
commit would flip the F11 removal gate green for tests still carrying the dead tag.

@FR-01.10
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts" / "lib"))

from fr_fold_map import audit_fold_map, merge_fold_maps, parse_fold_map  # noqa: E402

_FR_TABLE = (
    "## Functional Requirements\n\n"
    "| FR | Description | Priority | Layers |\n"
    "|----|----|----|----|\n"
    "| FR-01.28 | Embedded terminal | Must | unit |\n\n"
)


def test_a_cycle_does_not_swallow_the_folded_id_status_diagnostic():
    """Reviewer finding: the cycle skip must not hide *why the id itself* is wrong.

    Cycle detection is purely structural over the edge set and knows nothing about
    active/removed, so a looped id that is ALSO a live FR row still owes its
    `folded_id_still_active` report.
    """
    fm = parse_fold_map(
        f"{_FR_TABLE}## FR-Fold-Map\n\n"
        "| `FR-01.44` | `FR-01.45` | d | a |\n"
        "| `FR-01.45` | `FR-01.44` | d | b |\n"
    )
    kinds = sorted(d.kind for d in audit_fold_map(
        fm, active_ids={"FR-01.44"}, removed_ids=set()))
    assert kinds == ["cycle", "folded_id_still_active"]


# --------------------------------------------------------------------------
# Retirement beats folding (the F11 removal-gate false-green)
# --------------------------------------------------------------------------


def test_an_id_under_removed_requirements_is_reported_as_a_contradiction():
    """A removed id that is ALSO folded is a spec contradiction, not a silent no-op.

    Retirement wins (the rescue is refused by the callers), so the author must be told
    why their fold row is inert — otherwise the row simply appears not to work.
    """
    fm = parse_fold_map(f"{_FR_TABLE}## FR-Fold-Map\n\n| `FR-01.44` | `FR-01.28` | d | a |\n")
    kinds = [d.kind for d in audit_fold_map(
        fm, active_ids={"FR-01.28"}, removed_ids={"FR-01.44"})]
    assert kinds == ["folded_id_removed"]


# --------------------------------------------------------------------------
# Reviewer finding: conflicting_survivor content must not depend on spec order
# --------------------------------------------------------------------------


def test_conflicting_survivor_content_is_identical_in_either_merge_order():
    """The earlier determinism test used order-invariant defect kinds and proved nothing
    about the one kind that is genuinely order-sensitive."""
    a = parse_fold_map(f"{_FR_TABLE}## FR-Fold-Map\n\n| `FR-01.44` | `FR-01.28` | d | a |\n")
    b = parse_fold_map(f"{_FR_TABLE}## FR-Fold-Map\n\n| `FR-01.44` | `FR-01.99` | d | b |\n")
    forward = [d.as_dict() for d in merge_fold_maps([a, b]).defects]
    reverse = [d.as_dict() for d in merge_fold_maps([b, a]).defects]
    assert forward == reverse
    assert forward[0]["kind"] == "conflicting_survivor"
    assert forward[0]["raw"] == "FR-01.28 vs FR-01.99"


def test_three_specs_claiming_one_id_yield_ONE_conflict_defect():
    """One conflicted id = one defect, however many rivals claim it."""
    maps = [
        parse_fold_map(f"{_FR_TABLE}## FR-Fold-Map\n\n| `FR-01.44` | `{s}` | d | x |\n")
        for s in ("FR-01.28", "FR-01.99", "FR-01.99")
    ]
    merged = merge_fold_maps(maps)
    assert [d.kind for d in merged.defects] == ["conflicting_survivor"]
    assert "FR-01.44" not in merged.edges


# --------------------------------------------------------------------------
# Reviewer finding: a row with BOTH ids malformed must not read as a header
# --------------------------------------------------------------------------


def test_a_row_with_both_ids_malformed_is_still_reported():
    """`| FR-1.44 | FR-1.28 |` is plainly an attempted edge; treating it as a header row
    silently swallowed exactly the defect class the vocabulary exists to surface."""
    fm = parse_fold_map(f"{_FR_TABLE}## FR-Fold-Map\n\n| `FR-1.44` | `FR-1.28` | d | x |\n")
    assert fm.edges == {}
    assert [d.kind for d in fm.defects] == ["unparsable_row"]


def test_the_real_header_row_is_still_not_a_defect():
    """The discriminator must not over-fire on the actual table header."""
    fm = parse_fold_map(f"{_FR_TABLE}## FR-Fold-Map\n\n| `FR-01.44` | `FR-01.28` | d | a |\n")
    assert fm.defects == ()


