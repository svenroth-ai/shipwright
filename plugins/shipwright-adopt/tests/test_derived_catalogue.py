"""A derived catalogue must announce itself as derived (FR-01.13, trg-1aa5a8ab).

Onboarding writes a requirements catalogue by reading code. Nothing said so.
Everything downstream — traceability, coverage, drift — then measured against a
catalogue that *looked* confirmed and was not.

Two rules carry the weight here:

* **the marking lives above the table, never inside it.** `Basis` is a closed
  vocabulary and `fr_basis.classify` scores a value carrying a qualifier as
  malformed-and-blocking, so `code (unconfirmed)` would fail audit check `I5`;
  and `FR_TABLE_COLUMNS` is a two-sided contract shared with the greenfield
  producer, so a new column is a three-plugin change. The banner is prose, and
  the tests below prove a reader's view of the table is byte-unchanged by it.
* **the JSON and the rendered table cannot disagree.** Both derive their rows
  from `spec_table.effective_features`, and the round-trip test re-reads the
  rendered spec with the real `fr_table_reader` to prove it.

@FR-01.13
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from lib.derived_catalogue import (  # noqa: E402
    CONFIRMATION_DEDUP_KEY,
    ELICITATION_DOC,
    SUMMARY_REL,
    render_provenance_banner,
    summarize,
)
from lib.spec_table import render_fr_table  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts" / "lib"))
from fr_basis import classify  # noqa: E402
from fr_table_reader import read_active_fr_rows  # noqa: E402

FEATURES = [
    {"fr_id": "FR-01.01", "label": "Sign in", "source_file": "src/auth.ts"},
    {"fr_id": "FR-01.02", "label": "Dashboard", "url": "http://localhost:5173/"},
    {"fr_id": "FR-01.03", "label": "Something nobody evidenced"},
]


# --------------------------------------------------------------------------- #
# summarize — every row, and whether a person confirmed it
# --------------------------------------------------------------------------- #

def test_every_rendered_row_is_summarized() -> None:
    cat = summarize(FEATURES, split_name="01-adopted")
    assert [r.fr_id for r in cat.requirements] == ["FR-01.01", "FR-01.02", "FR-01.03"]
    assert cat.total == 3


def test_basis_matches_the_table_vocabulary() -> None:
    cat = summarize(FEATURES, split_name="01-adopted")
    assert [r.basis for r in cat.requirements] == ["code", "observed", "assumed"]
    assert cat.by_basis == {"assumed": 1, "code": 1, "observed": 1}


def test_nothing_adopt_derives_today_counts_as_confirmed() -> None:
    """`code` / `observed` / `assumed` all mean *no person has said so*."""
    cat = summarize(FEATURES, split_name="01-adopted")
    assert cat.unconfirmed == 3
    assert cat.confirmed == 0
    assert all(r.confirmed is False for r in cat.requirements)


def test_an_interview_backed_row_is_confirmed() -> None:
    """The one vocabulary value that means a human told us. Adopt cannot emit it
    today; the rule is written so a future elicitation pass changes the count
    without touching this module."""
    cat = summarize([{"fr_id": "FR-01.01", "label": "x", "basis": "interview"}],
                    split_name="01-adopted")
    assert cat.confirmed == 1
    assert cat.unconfirmed == 0


def test_a_zero_detection_repo_summarizes_the_placeholder_row() -> None:
    """`render_fr_table` synthesizes one placeholder row when detection found
    nothing. The summary must describe THAT row — a count of 0 beside a table
    with a row in it is the drift this whole card exists to stop."""
    cat = summarize([], split_name="01-adopted")
    assert cat.total == 1
    assert cat.requirements[0].fr_id == "FR-01.01"
    assert cat.requirements[0].basis == "assumed"
    assert cat.unconfirmed == 1


# --------------------------------------------------------------------------- #
# The banner — visible to a human, invisible to every table reader
# --------------------------------------------------------------------------- #

def test_banner_states_the_count_and_that_nobody_confirmed_it() -> None:
    banner = render_provenance_banner(summarize(FEATURES, split_name="01-adopted"))
    assert "3" in banner
    assert "unconfirmed" in banner.lower()
    assert "derived" in banner.lower()


def test_banner_points_at_the_machine_readable_copy_and_the_follow_up() -> None:
    banner = render_provenance_banner(summarize(FEATURES, split_name="01-adopted"))
    assert SUMMARY_REL in banner
    assert "requirement-elicitation.md" in banner
    assert CONFIRMATION_DEDUP_KEY in banner


def test_banner_contains_no_table_row() -> None:
    """The load-bearing property. Every FR-table consumer in the framework
    (`fr_table_reader`, `traceability_layers`, compliance Group I) is line-based
    on a leading `|`; a banner line that started with one would be parsed as a
    requirement row or, worse, as a header that invalidates the column map."""
    banner = render_provenance_banner(summarize(FEATURES, split_name="01-adopted"))
    offenders = [ln for ln in banner.splitlines() if ln.strip().startswith("|")]
    assert not offenders, f"banner emits table-shaped lines: {offenders}"


def test_banner_interpolates_no_free_text() -> None:
    """Counts and fixed vocabulary only — no detected name, description, route or
    split name reaches the banner. That is why a pipe in a detected description
    cannot leak into it (external review G4); the round-trip test below proves
    the property empirically rather than by sanitising after the fact."""
    hostile = [
        {"fr_id": "FR-01.01", "label": "a | b", "description": "x | y",
         "source_file": "src/a | b.ts", "route": "/a|b"},
    ]
    banner = render_provenance_banner(summarize(hostile, split_name="01|adopted"))
    assert "|" not in banner


# --------------------------------------------------------------------------- #
# Round-trip: banner + table, read back by the real reader (external review O8)
# --------------------------------------------------------------------------- #

def _rendered_section(features, split_name: str) -> str:
    cat = summarize(features, split_name=split_name)
    return (
        "## Functional Requirements\n\n"
        + render_provenance_banner(cat)
        + "\n\n"
        + render_fr_table(features, split_name=split_name)
        + "\n"
    )


def test_the_reader_sees_the_same_rows_with_and_without_the_banner() -> None:
    with_banner = read_active_fr_rows(_rendered_section(FEATURES, "01-adopted"))
    without = read_active_fr_rows(
        "## Functional Requirements\n\n"
        + render_fr_table(FEATURES, split_name="01-adopted") + "\n"
    )
    assert [r.cells for r in with_banner] == [r.cells for r in without]
    assert len(with_banner) == 3


def test_json_summary_matches_the_table_the_reader_actually_parses() -> None:
    """The anti-drift contract. The summary is not allowed to describe a
    catalogue different from the one handed over, so it is compared against the
    RENDERED document, parsed by the shared reader — not against its own input."""
    cat = summarize(FEATURES, split_name="01-adopted")
    rows = read_active_fr_rows(_rendered_section(FEATURES, "01-adopted"))
    assert [r.id for r in rows] == [r.fr_id for r in cat.requirements]
    assert [r.basis_cell for r in rows] == [r.basis for r in cat.requirements]
    assert len(rows) == cat.total


def test_round_trip_survives_pipes_in_detected_text() -> None:
    """A repo whose code comments contain `|` — the FV-3 class. The escaping
    lives in `spec_table`; this pins that the banner did not re-open it."""
    hostile = [{"fr_id": "FR-01.01", "label": "a | b", "description": "c | d",
                "source_file": "src/x.ts"}]
    rows = read_active_fr_rows(_rendered_section(hostile, "01-adopted"))
    assert len(rows) == 1
    assert rows[0].id == "FR-01.01"
    assert rows[0].basis_cell == "code"


def test_zero_detection_round_trip_agrees_too() -> None:
    cat = summarize([], split_name="01-adopted")
    rows = read_active_fr_rows(_rendered_section([], "01-adopted"))
    assert len(rows) == cat.total == 1
    assert rows[0].id == cat.requirements[0].fr_id


@pytest.mark.parametrize("features", [FEATURES, []])
def test_every_emitted_basis_passes_the_audit_vocabulary(features) -> None:
    """A `Basis` value outside the closed set is a HARD audit failure (`I5`), so
    the summary must never invent one — this is also why `unconfirmed` is not
    expressed as a qualifier on the cell."""
    for req in summarize(features, split_name="01-adopted").requirements:
        assert classify(req.basis).kind == "known", req.basis


# --------------------------------------------------------------------------- #
# The banner states what is true of THIS catalogue (external code review, round 3)
# --------------------------------------------------------------------------- #

_INTERVIEWED = {"fr_id": "FR-01.09", "label": "Checkout", "basis": "interview"}


def test_a_partly_confirmed_catalogue_does_not_claim_nobody_confirmed_it() -> None:
    """The block's whole job is honesty, so it must not keep saying "nobody" once
    the elicitation follow-up starts landing answers."""
    banner = render_provenance_banner(
        summarize([*FEATURES, _INTERVIEWED], split_name="01-adopted"))
    assert "nobody has confirmed" not in banner
    assert "3 of these 4 requirements" in banner
    assert "**1** have been worked through with a person" in banner
    assert CONFIRMATION_DEDUP_KEY in banner


def test_a_fully_confirmed_catalogue_says_so_and_asks_for_nothing() -> None:
    """No unconfirmed rows means no follow-up is filed, so the block must not
    point at a card that does not exist."""
    banner = render_provenance_banner(summarize([_INTERVIEWED], split_name="01-adopted"))
    assert "have been confirmed with a person" in banner
    assert "unconfirmed" not in banner
    assert CONFIRMATION_DEDUP_KEY not in banner
    assert ELICITATION_DOC not in banner


def test_an_all_derived_catalogue_still_says_nobody() -> None:
    banner = render_provenance_banner(summarize(FEATURES, split_name="01-adopted"))
    assert "nobody has confirmed them yet" in banner


@pytest.mark.parametrize("features", [FEATURES, [*FEATURES, _INTERVIEWED], [_INTERVIEWED]])
def test_no_banner_variant_emits_a_table_row(features) -> None:
    banner = render_provenance_banner(summarize(features, split_name="01-adopted"))
    assert not [ln for ln in banner.splitlines() if ln.strip().startswith("|")]
