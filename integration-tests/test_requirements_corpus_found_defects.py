"""Freeze the defects found while BUILDING the golden corpus (FV-3, FV-4, FV-5).

Campaign "Requirements Catalog" sub-iterate S1. These three are NOT in the
campaign SPEC -- the survey turned them up, and they have been added to S4's
acceptance criteria plus filed as a triage anchor so they cannot be lost if S4
is descoped. All three are fixed by the same change: S4's single header-driven
reader.

Same rule as the SPEC-named verdicts: every assertion here pins behaviour that
is WRONG, deliberately. Do not correct one into agreement -- see
``requirements_corpus/frozen_bugs.py``.

@FR-01.10
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from requirements_corpus.collect import collect_all  # noqa: E402
from requirements_corpus.frozen_bugs import FROZEN_BUGS, SPEC_NAMED  # noqa: E402
from requirements_corpus.probe import ProbeFailed, probe  # noqa: E402


@pytest.fixture(scope="module")
def matrix():
    """Collect once per module -- one subprocess per realm, not per test."""
    return collect_all()["targets"]


def _probe(name: str, fixture: str):
    """Fail the test loudly if the probe crashes -- never silently pass.

    Raises rather than calling ``pytest.fail`` so the function has exactly one
    exit path per branch. ``pytest.fail`` does raise, but nothing in the
    signature says so, and a reader (or a static analyser) sees a branch that
    falls through and returns ``None`` -- which on a harness whose whole point
    is "a crashed probe must never read as a passing check" is the wrong shape
    to leave lying around.
    """
    try:
        return probe(name, fixture)
    except ProbeFailed as exc:
        raise AssertionError(str(exc)) from exc


# ---------------------------------------------------------------------------
# FV-3/4/5 -- found while building this harness; added to S4's AC + triage
# ---------------------------------------------------------------------------

def test_fv3_rtm_displays_wrong_requirement_text(matrix):
    """FROZEN-BUG (FV-3): a row wider than its header shifts the body column.

    The `07-header-blind` spec declares three columns and carries a five-cell
    row. ``drift_parsers``/``rtm`` are header-blind, so regex group 4 fires and
    the *fourth* cell is read as the requirement text. The RTM renders "extra"
    where the requirement says "ok".

    This is live wrong DATA in a shipped audit artifact, not a parse
    divergence. Not in the campaign SPEC -- found building this harness.

    Flipped by: S4 (selection by column name).
    """
    rows = matrix["parse.drift_parsers.parse_fr_table"][
        "fixtures"]["mixed-shape"]["per_spec"][
        ".shipwright/planning/07-header-blind/spec.md"]["value"]
    assert [r["id"] for r in rows] == ["FR-07.01"]
    assert rows[0]["text"] == "extra"  # FROZEN-BUG (FV-3) -- should be "ok"


def test_fv4_group_i_drops_every_row_on_an_fr_header(matrix):
    """FROZEN-BUG (FV-4): header 'FR' instead of 'ID' -> zero rows, silently.

    ``group_i._column_map`` requires ``cells[0] == "id"`` exactly. On the
    traceability-fixture shape it returns None, the mapping stays None, and the
    whole file is dropped -- after which all four hygiene checks report against
    zero rows, which is itself green (FV-2). Two bugs compose into silence.

    Flipped by: S4.
    """
    rows = matrix["parse.group_i._scan_one_spec"][
        "fixtures"]["mixed-shape"]["per_spec"][
        ".shipwright/planning/05-fixture-fr/spec.md"]["value"]
    assert rows == []  # FROZEN-BUG (FV-4) -- FR-05.01 is right there in the file


def test_fv5_group_i_drops_rows_after_a_later_heading(matrix):
    """FROZEN-BUG (FV-5): the column mapping resets at EVERY heading.

    In the `edge` fixture, FR-01.20 sits under '## Next' with no repeated header
    row. group_i loses it; all four other parsers keep it. Pinning the contrast
    is the point -- it shows the row is well-formed and only this parser is
    blind to it.

    Flipped by: S4.
    """
    per_spec = matrix
    spec = ".shipwright/planning/01-live/spec.md"

    def ids(target):
        cell = per_spec[target]["fixtures"]["edge"]["per_spec"][spec]
        return [r["id"] for r in cell["value"]]

    assert "FR-01.20" not in ids("parse.group_i._scan_one_spec")  # FROZEN-BUG
    assert "FR-01.20" in ids("parse.drift_parsers.parse_fr_table")
    assert "FR-01.20" in ids("parse._backfill_spec_parse.parse_frs")
    assert "FR-01.20" in ids("parse._requirement_parse.parse_requirements")


# ---------------------------------------------------------------------------
# Unsorted walks -- pinned against a controlled seam, not against luck
# ---------------------------------------------------------------------------

def test_unsorted_walk_tracks_enumeration_order():
    """``validate_adoption._validate_spec`` acts on whatever comes back first.

    It does ``list(planning.rglob("spec.md"))`` with no sort and takes ``[0]``,
    so WHICH spec is validated depends on filesystem iteration order. Asserting
    a specific path would pin whichever order this machine produced and flake
    between NTFS and ext4; sorting the result would hide the behaviour entirely.

    So the seam is controlled instead: enumerate forward, then reversed, and
    show the outcome tracks the order it was handed. That is the actual
    behavioural claim -- "this walk has no order of its own".
    """
    result = _probe("unsorted_seam", "edge")
    assert result["forward"] != result["reverse"], (
        "the walk stopped tracking enumeration order -- if a sort was added, "
        "that is a behaviour change S2 must declare"
    )


def test_unsorted_walk_a2_tracks_enumeration_order():
    """The SECOND masked target needs its own seam probe.

    Both ``validate_adoption._validate_spec`` and
    ``adopt_compliance.check_a2_spec_has_frs`` are ``order_sensitive``, so both
    have their picked path masked out of the golden matrix. For a while only
    the first had a compensating probe -- which meant adding ``sorted()`` to
    check_a2's rglob would move no golden cell and no test would look. A walk
    would have stopped being order-dependent and the harness would have
    certified "no behaviour change".

    Masking without a compensating probe is not a safety measure, it is a
    blind spot with good manners. (Caught in adversarial review.)
    """
    result = _probe("unsorted_seam_a2", "edge")
    assert result["forward"] != result["reverse"], (
        "check_a2_spec_has_frs stopped tracking enumeration order -- if a sort "
        "was added, that is a behaviour change S2 must declare"
    )


# ---------------------------------------------------------------------------
# The frozen-bug manifest itself
# ---------------------------------------------------------------------------

def test_every_frozen_bug_names_its_flipping_step():
    """A frozen bug with no flip step is a bug someone will silently 'fix'."""
    for bug_id, info in FROZEN_BUGS.items():
        assert info["flipped_by"].startswith("S"), bug_id
        assert info["what"] and info["why_not_fixed"], bug_id


def test_frozen_bug_cells_exist_in_the_matrix(matrix):
    """Every cell a frozen bug points at must actually be in the golden file.

    Without this, a fixture rename would orphan the rationale: the surprising
    value stays in golden.json while the explanation silently stops resolving.
    """
    targets = matrix
    for bug_id, info in FROZEN_BUGS.items():
        for target, fixture, spec in info["cells"]:
            assert target in targets, f"{bug_id}: unknown target {target}"
            cell = targets[target]["fixtures"][fixture]
            assert spec in cell["per_spec"], f"{bug_id}: {fixture}/{spec} missing"


def test_spec_named_bugs_are_marked_apart_from_discovered_ones():
    """FV-1/FV-2 came from the campaign SPEC; FV-3/4/5 were found here.

    Keeping the provenance explicit matters: the three discovered ones are the
    reason S4's acceptance criteria were widened, and a reader needs to know
    they are not part of the original plan.
    """
    assert SPEC_NAMED == ("FV-1", "FV-2")
    for bug_id in ("FV-3", "FV-4", "FV-5"):
        assert FROZEN_BUGS[bug_id]["found_by"] == (
            "iterate-2026-07-18-requirements-golden-corpus"
        )
