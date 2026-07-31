"""The prose contracts the capped fall-through depends on.

Two doc changes in iterate-2026-07-31-it5-classification-calibration are
load-bearing rather than explanatory, so they are pinned rather than trusted:

1. **Quick Scout runs the diff-driven detectors.** Capping the fall-through at
   `small` routes most no-keyword runs to Quick Scout instead of Thorough. The
   cap's justification is that under-classification is recoverable at Stage 2 —
   which only holds if the Stage 2 that actually runs can still see
   cross-component changes. Stage 1 raises `cross_component` from *message*
   keywords alone, and the F11 verifier `check_integration_coverage` green-SKIPs
   below medium, so this step is the only place a diff-shaped signal reaches the
   estimate. If it is edited out, the cap silently loses its safety net.

2. **F5c records `prior_source`.** It is what makes the fall-through auditable
   at all, and what unblocks the better calibration (median over
   keyword-classified runs only) once the window fills.
"""

from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
REFS = PLUGIN_ROOT / "skills" / "iterate" / "references"
PLANNING = REFS / "iteration-planning.md"
F5C = REFS / "F5c.md"


def _quick_scout_section() -> str:
    text = PLANNING.read_text(encoding="utf-8")
    start = text.find("### Quick Scout")
    assert start != -1, "iteration-planning.md has no '### Quick Scout' section"
    nxt = text.find("### ", start + 4)
    return text[start:nxt if nxt != -1 else len(text)]


@pytest.mark.covers("FR-01.11")
@pytest.mark.parametrize("detector", [
    "is_cross_component_change",
    "is_ci_supplychain_change",
    "is_io_boundary_change",
    "touches_build_files",
])
def test_quick_scout_names_the_diff_driven_detectors(detector):
    assert detector in _quick_scout_section(), (
        f"Quick Scout must run {detector} over the changed-file list. Stage 1 "
        f"has no diff, so removing this step leaves the capped fall-through "
        f"with no diff-shaped signal before complexity locks."
    )


@pytest.mark.covers("FR-01.11")
def test_quick_scout_still_checks_cross_split():
    """Thorough Scout's cross-split step had to reach Quick Scout too.

    `cross_split` floors at medium, and it is one of the four positive signals
    SKILL.md §E names as a way to reach medium — it cannot live only in the
    depth that the cap stops routing runs to.
    """
    assert "crosses split boundaries" in _quick_scout_section()


@pytest.mark.covers("FR-01.11")
def test_f5c_template_records_prior_source():
    text = F5C.read_text(encoding="utf-8")
    assert '"prior_source"' in text, (
        "the F5c entry template must carry prior_source — without it the "
        "complexity ladder cannot be audited in either direction"
    )
    for level in ("keyword", "history", "default"):
        assert level in text, f"F5c must document prior_source value {level!r}"
