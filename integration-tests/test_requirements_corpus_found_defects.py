"""The defects found while BUILDING the golden corpus (FV-3, FV-4, FV-5).

Campaign "Requirements Catalog", written at S1. These three were NOT in the
campaign SPEC -- the survey turned them up, and they were added to S4's
acceptance criteria plus filed as a triage anchor so they could not be lost if
S4 were descoped. **All three were flipped by S4** (a single header-driven
reader), and the assertions below now pin the corrected behaviour together with
the mechanism each one had, so the golden diff that moved those cells stays
explained.

Do not "correct" an assertion into agreement with a surprising value -- see
``requirements_corpus/frozen_bugs.py``.

@FR-01.10
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from requirements_corpus.collect import collect_all  # noqa: E402
from requirements_corpus.frozen_bugs import (  # noqa: E402
    FLIPPED,
    FROZEN_BUGS,
    SPEC_NAMED,
    STILL_FROZEN,
)
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

def test_fv3_rtm_displays_the_requirement_text_its_header_names(matrix):
    """FLIPPED by S4 (was FROZEN-BUG FV-3).

    The `07-header-blind` spec declares three columns and carries a five-cell
    row. The old header-blind regex let group 4 fire, so the *fourth* cell was
    read as the requirement text and the RTM rendered "extra" where the
    requirement says "ok" -- live wrong DATA in a shipped audit artifact, not a
    parse divergence. Selection is now by column NAME, so a row wider than its
    header cannot shift the body.
    """
    rows = matrix["parse.drift_parsers.parse_fr_table"][
        "fixtures"]["mixed-shape"]["per_spec"][
        ".shipwright/planning/07-header-blind/spec.md"]["value"]
    assert [(r["id"], r["text"]) for r in rows] == [("FR-07.01", "ok")]


def test_fv3_the_second_occurrence_in_the_malformed_fixture_is_fixed_too(matrix):
    """The same bug had TWO sites in the corpus; only one was described.

    `malformed/FR-01.03` is the identical shape (3-column header, 5-cell row).
    Asserting it separately is what stops a fix that special-cases one fixture
    from reading as a fix of the class.
    """
    # rtm is the one parser registered as a WALK, so its cell is a flat list
    # over the whole tree rather than a per_spec map (registry.py says so).
    rows = matrix["parse.rtm.collect_requirements"]["fixtures"]["malformed"]["value"]
    texts = {r["id"]: r["text"] for r in rows}
    assert texts["FR-01.03"] == "ok"


def test_fv4_group_i_reads_a_table_whose_id_column_is_headed_fr(matrix):
    """FLIPPED by S4 (was FROZEN-BUG FV-4).

    ``group_i._column_map`` required ``cells[0] == "id"`` exactly. On the
    traceability-fixture shape it returned None, the mapping stayed None, and
    the whole file was dropped -- after which all four hygiene checks reported
    against zero rows, which is itself green (FV-2). Two bugs composed into
    silence. A header row is now recognised by naming a Priority column, so the
    id column's own heading is free.
    """
    rows = matrix["parse.group_i._scan_one_spec"][
        "fixtures"]["mixed-shape"]["per_spec"][
        ".shipwright/planning/05-fixture-fr/spec.md"]["value"]
    assert [r["id"] for r in rows] == ["FR-05.01"]


def test_fv5_every_parser_keeps_rows_after_a_later_heading(matrix):
    """FLIPPED by S4 (was FROZEN-BUG FV-5).

    In the `edge` fixture, FR-01.20 sits under '## Next' with no repeated header
    row. group_i used to reset its column mapping at EVERY heading and lose it
    while all four other parsers kept it. The contrast is now agreement -- which
    is the assertion worth keeping, because "all five agree" is the property S4
    actually delivers.
    """
    spec = ".shipwright/planning/01-live/spec.md"

    def ids(target):
        cell = matrix[target]["fixtures"]["edge"]["per_spec"][spec]
        return [r["id"] for r in cell["value"]]

    for target in (
        "parse.group_i._scan_one_spec",
        "parse.drift_parsers.parse_fr_table",
        "parse._backfill_spec_parse.parse_frs",
        "parse._requirement_parse.parse_requirements",
    ):
        assert "FR-01.20" in ids(target), target


def test_the_five_parsers_agree_on_which_ids_a_spec_declares(matrix):
    """The property S4 exists to establish, asserted directly.

    Every divergence the corpus recorded was ultimately one of five parsers
    disagreeing about which rows a file contains. ``_backfill`` and
    ``_requirement_parse`` see removed rows that the two live-only readers
    filter, so compare on ACTIVE ids only; group_i's default view is live rows
    as well.
    """
    spec = ".shipwright/planning/01-live/spec.md"

    def active_ids(target):
        cell = matrix[target]["fixtures"]["edge"]
        # rtm is registered as a WALK, so its cell is a flat list over the whole
        # tree; the other four are keyed per spec file. Narrow both to one spec.
        if "per_spec" in cell:
            rows = cell["per_spec"][spec]["value"]
        else:
            rows = [r for r in cell["value"] if r.get("spec_path") == spec]
        return sorted(
            r["id"] for r in rows
            if r.get("status", "active") == "active" and not r.get("retired")
        )

    reference = active_ids("parse.drift_parsers.parse_fr_table")
    assert reference, "the edge fixture must declare at least one active FR"
    for target in (
        "parse.rtm.collect_requirements",
        "parse._backfill_spec_parse.parse_frs",
        "parse._requirement_parse.parse_requirements",
        "parse.group_i._scan_one_spec",
    ):
        assert active_ids(target) == reference, target


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
        assert info["state"] in ("frozen", "flipped"), bug_id


def test_a_flipped_entry_records_which_run_flipped_it_and_what_it_reads_now():
    """A flipped entry must not degrade into a deleted one.

    Deleting the record would leave the golden diff that moved those cells
    unexplained forever -- the same failure mode the frozen entries exist to
    prevent, displaced in time. So a flip is an EDIT that adds provenance, and
    this test is what makes that a rule rather than a habit.
    """
    assert set(FLIPPED) == {"FV-1", "FV-3", "FV-4", "FV-5"}
    assert STILL_FROZEN == ("FV-2",), "FV-2 belongs to S6, not S4"
    for bug_id in FLIPPED:
        info = FROZEN_BUGS[bug_id]
        assert info["flipped_in"], bug_id
        assert info["now"], bug_id
    for bug_id in STILL_FROZEN:
        assert "now" not in FROZEN_BUGS[bug_id], bug_id


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
