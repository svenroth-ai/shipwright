"""Shipped-form acceptance fallback + table-row description exemption
(campaign REQ3.04, sub-iterate R0).

Split out of test_spec_checks.py rather than appended there: that file
already carries a grandfathered bloat-baseline entry, so growing it further
would ratchet past its `current` ceiling (see test_spec_checks_s3_miniplan_gate.py
for the same pattern).

Covers ``lib.spec_parser.parse_fr_headings``'s shipped-form fallback (S2 —
bare bullets under a heading with no bold label at all, the shape
`/shipwright-project` and `/shipwright-adopt` actually emit) and
``compute_fr_coherence``'s table-row exemption (S3 — a heading whose id is
also a row of the file's own FR table is a detail section, not a
definition, so it is never reported as missing a description).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from lib import spec_parser  # noqa: E402


@pytest.fixture
def proj(tmp_path: Path) -> Path:
    (tmp_path / ".shipwright" / "agent_docs").mkdir(parents=True, exist_ok=True)
    return tmp_path


def _write_top_spec(proj: Path, content: str) -> None:
    (proj / ".shipwright" / "agent_docs" / "spec.md").write_text(content, encoding="utf-8")


# ---------------------------------------------------------------------------
# spec_parser — shipped-form acceptance fallback (S2, campaign REQ3.04 R0)
# ---------------------------------------------------------------------------


def test_parse_fr_headings_shipped_form_fallback():
    """No bold label at all: bare bullets directly under the heading (the
    shape `/shipwright-project` and `/shipwright-adopt` actually emit) still
    count as acceptance."""
    content = (
        "### FR-01.01 — Title\n"
        "- (E) Given a change, when it runs, then it works.\n"
    )
    frs = spec_parser.parse_fr_headings(content)
    assert len(frs) == 1
    assert frs[0].has_acceptance()
    assert "Given a change" in frs[0].acceptance


def test_parse_fr_headings_fallback_requires_adjacency():
    """A bullet list further down, after a prose paragraph, does NOT count.

    Without this, the fallback would reach into free-text documents (e.g.
    `.shipwright/planning/iterate/*.md`) and read an unrelated bullet list
    under an accidentally FR-shaped heading as that FR's acceptance.
    """
    content = (
        "### FR-01.01 — Title\n"
        "Some prose discussing the requirement.\n"
        "\n"
        "- this bullet is not adjacent to the heading\n"
    )
    frs = spec_parser.parse_fr_headings(content)
    assert len(frs) == 1
    assert not frs[0].has_acceptance()


def test_parse_fr_headings_fallback_leading_placeholder_does_not_reach_a_later_list():
    """External code review, high severity (2026-08-25): a leading placeholder
    bullet must not let a LATER, non-adjacent list (after prose) count either.
    Only the first, contiguous list is ever read."""
    content = (
        "### FR-01.01 — Title\n"
        "- [ ] TBD\n"
        "\n"
        "Some prose in between.\n"
        "\n"
        "- a real-looking but non-adjacent bullet\n"
    )
    frs = spec_parser.parse_fr_headings(content)
    assert len(frs) == 1
    assert not frs[0].has_acceptance()


def test_parse_fr_headings_fallback_rejects_placeholder_only():
    content = (
        "### FR-01.01 — Title\n"
        "- [ ] TBD\n"
    )
    frs = spec_parser.parse_fr_headings(content)
    assert len(frs) == 1
    assert not frs[0].has_acceptance()


def test_parse_fr_headings_fallback_yields_nothing_without_bullets_or_label():
    content = "### FR-01.01 — Title\nJust a sentence, no bullets, no label.\n"
    frs = spec_parser.parse_fr_headings(content)
    assert len(frs) == 1
    assert not frs[0].has_acceptance()


def test_description_extraction_skips_labelled_only_body():
    """A section carrying only an `**Acceptance Criteria:**` label has NO
    description — the derivation must not read that labelled line as prose.

    Own unit test per the R0 acceptance criteria: `parse_fr_headings` never
    grew a description fallback (only acceptance did, S2), so this pins that
    invariant explicitly rather than leaving it to be implied by
    `test_compute_fr_coherence_reports_gaps`'s FR-3 case alone.
    """
    content = "## FR-3: No desc\n**Acceptance Criteria:** only accept.\n"
    frs = spec_parser.parse_fr_headings(content)
    assert len(frs) == 1
    assert not frs[0].has_description()
    assert frs[0].has_acceptance()


# ---------------------------------------------------------------------------
# spec_parser — table-row exemption for missing_description (S3, R0)
# ---------------------------------------------------------------------------


def test_compute_fr_coherence_table_row_exempts_missing_description(proj: Path):
    """A heading whose id is ALSO a row of the file's own FR table is a
    DETAIL section, not a definition — its description lives in the table
    cell, so it is not reported as missing a description."""
    _write_top_spec(proj, (
        "| ID | Name | Priority | Description | Basis | Layers |\n"
        "|---|---|---|---|---|---|\n"
        "| FR-01.01 | Thing | Must | Does the thing. | interview | unit |\n"
        "\n"
        "### FR-01.01 — Thing\n"
        "- (E) Given a change, when it runs, then it works.\n"
    ))
    report = spec_parser.compute_fr_coherence(proj)
    assert report.total_frs == 1
    assert report.missing_description == ()
    assert report.missing_acceptance == ()
    assert report.missing_both == ()
    assert report.ok


def test_compute_fr_coherence_table_row_exemption_does_not_cover_acceptance(proj: Path):
    """The table-row exemption is scoped to the description axis only — a
    table-row heading with no criteria still reports missing_acceptance."""
    _write_top_spec(proj, (
        "| ID | Name | Priority | Description | Basis | Layers |\n"
        "|---|---|---|---|---|---|\n"
        "| FR-01.01 | Thing | Must | Does the thing. | interview | unit |\n"
        "\n"
        "### FR-01.01 — Thing\n"
        "No bullets here at all.\n"
    ))
    report = spec_parser.compute_fr_coherence(proj)
    assert report.missing_description == ()
    assert any("FR-01.01" in x for x in report.missing_acceptance)
    assert report.missing_both == ()


def test_compute_fr_coherence_table_row_with_empty_cell_does_not_exempt(proj: Path):
    """External plan review (DeepSeek, 2026-08-25): a table ROW existing is not
    the same as a table DESCRIPTION existing. A row whose Description cell is
    blank must not silence a real missing_description gap."""
    _write_top_spec(proj, (
        "| ID | Name | Priority | Description | Basis | Layers |\n"
        "|---|---|---|---|---|---|\n"
        "| FR-01.01 | Thing | Must |  | interview | unit |\n"
        "\n"
        "### FR-01.01 — Thing\n"
        "- (E) Given a change, when it runs, then it works.\n"
    ))
    report = spec_parser.compute_fr_coherence(proj)
    assert any("FR-01.01" in x for x in report.missing_description)
