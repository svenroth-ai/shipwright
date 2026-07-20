"""Adopt renders the converged FR table (campaign S5).

Two rules carry real weight here. ``basis_for`` answers campaign open question 3
— *"`enrichment` maps to `code`/`observed` depending on origin — is that
lossy?"* — with **no**, because the discriminator was already present at the
point the old ``Source`` cell was rendered. And every cell is escaped, which the
hand-written f-string it replaces never did: a detected description containing a
pipe silently split into extra columns, which is the FV-3 class (an RTM showing
the wrong requirement text) manufactured from any repo whose code comments
contain a ``|``.

@FR-01.13
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from lib.spec_table import basis_for, render_fr_table  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts" / "lib"))
from fr_table_shape import FR_TABLE_HEADER  # noqa: E402


# ---------------------------------------------------------------------------
# Basis — the discriminator the old Source column collapsed
# ---------------------------------------------------------------------------


def test_a_feature_read_from_source_is_code() -> None:
    assert basis_for({"source_file": "src/auth.ts"}) == "code"


def test_a_crawl_only_feature_is_observed() -> None:
    """Seen in the running application — that is what the Playwright crawl saw."""
    assert basis_for({"url": "https://example.test/login"}) == "observed"


def test_source_file_wins_when_both_are_present() -> None:
    """Reading the code is the stronger evidence, so it is the one recorded."""
    assert basis_for({"source_file": "src/a.ts", "url": "https://x/a"}) == "code"


def test_a_feature_with_no_evidence_is_assumed() -> None:
    """`assumed` exists precisely so a guess cannot later read as fact."""
    assert basis_for({"label": "Something"}) == "assumed"


@pytest.mark.parametrize("placeholder", ["—", "-", "", "  ", "n/a", "TBD", "?"])
def test_a_placeholder_source_file_is_not_evidence(placeholder: str) -> None:
    """Regression: ``generate_adoption_artifacts`` defaults an unmatched
    ``source_file`` to the literal ``"—"``, because that was a *display*
    placeholder for the old ``Source`` column. A truthiness test reads it as a
    real path and labels every crawl-only page ``code`` — the exact inversion of
    what the crawl observed. Caught by the additive-merge test that asserts a
    crawled route's origin.
    """
    assert basis_for({"source_file": placeholder, "url": "https://x/a"}) == "observed"
    assert basis_for({"source_file": placeholder}) == "assumed"


# ---------------------------------------------------------------------------
# The rendered table
# ---------------------------------------------------------------------------


def _cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def test_the_table_opens_with_the_canonical_header() -> None:
    out = render_fr_table([{"fr_id": "FR-01.01", "label": "A"}], split_name="01-adopted")
    lines = out.splitlines()
    assert lines[0] == FR_TABLE_HEADER
    assert lines[1].count("---") == 7


def test_every_layers_cell_carries_the_inferred_marker() -> None:
    """Machine-derived layers keep an adopted repo on advisory provenance rather
    than collapsing it into the hard-gate regime against absent test links."""
    out = render_fr_table([
        {"fr_id": "FR-01.01", "label": "Dash", "source_file": "src/pages/a.tsx",
         "framework": "next-app-router"},
        {"fr_id": "FR-01.02", "label": "Api", "source_file": "api/x.py",
         "framework": "fastapi"},
    ], split_name="01-adopted")
    for line in out.splitlines()[2:]:
        assert "(inferred)" in _cells(line)[6]


def test_area_is_rendered_from_the_group_digit() -> None:
    out = render_fr_table([{"fr_id": "FR-01.01", "label": "A"}], split_name="01-adopted")
    assert _cells(out.splitlines()[2])[1] == "Adopted"


def test_a_pipe_in_a_description_does_not_create_a_column() -> None:
    """The defect the f-string this replaces could manufacture.

    Asserted through the REAL reader rather than a naive ``split("|")``: the
    escape is only meaningful if the consumer resolves it, so checking that the
    producer emitted a backslash would prove half a contract. The naive splitter
    used elsewhere in this module sees eight cells here — which is precisely the
    failure mode, and why this one case goes the whole way round.
    """
    from fr_table_reader import read_fr_rows

    out = render_fr_table([
        {"fr_id": "FR-01.01", "label": "A", "description": "Returns 200 | ok"},
    ], split_name="01-adopted")
    assert r"\|" in out
    (row,) = read_fr_rows(out)
    assert len(row.cells) == 7
    assert row.text == "Returns 200 | ok"


def test_a_newline_in_a_description_does_not_break_the_row() -> None:
    out = render_fr_table([
        {"fr_id": "FR-01.01", "label": "A", "description": "line one\nline two"},
    ], split_name="01-adopted")
    assert len(out.splitlines()) == 3


def test_no_detected_features_still_yields_a_well_formed_table() -> None:
    """A header with no rows is a state a gate has to special-case; an editable
    placeholder row is more useful. `assumed` is its honest basis."""
    out = render_fr_table([], split_name="01-adopted")
    lines = out.splitlines()
    assert lines[0] == FR_TABLE_HEADER
    assert len(lines) == 3
    cells = _cells(lines[2])
    assert cells[0] == "FR-01.01"
    assert cells[5] == "assumed"
    assert "(inferred)" in cells[6]


@pytest.mark.parametrize("feature,expected", [
    ({"source_file": "src/pages/home.tsx", "framework": "next-app-router"}, "unit, e2e"),
    ({"source_file": "db/migrations/001.sql"}, "unit, integration"),
    ({"source_file": "api/handler.py", "framework": "fastapi"}, "unit"),
])
def test_layers_follow_the_existing_surface_inference(feature: dict, expected: str) -> None:
    """S5 changes the SHAPE, not the inference — those values are unchanged."""
    feature = {"fr_id": "FR-01.01", "label": "A", **feature}
    out = render_fr_table([feature], split_name="01-adopted")
    assert _cells(out.splitlines()[2])[6] == f"{expected} (inferred)"
