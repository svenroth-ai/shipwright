"""The FR-table description exemption must require a REAL description cell,
not a fallback onto the Name cell (iterate-2026-08-25-fr-criteria-parser-pin,
merged from trg-467b7b2f, doubt-review round 1).

``compute_fr_coherence`` (S5) exempts a heading with no ``**Description:**``
body from ``missing_description`` when its own FR table row carries a
non-empty ``text`` cell (``spec_parser.py``'s ``table_row_ids`` set) — the
FR is a "detail section", the table already describes it. ``fr_table_reader``
picks that cell via ``TITLE_COLS = ("description", "name", "text",
"requirement", "title")``, first match wins: on a table with a ``Name``
column but NO ``Description`` column, the exemption fires on the Name cell —
a short label, not a description — and a heading with genuinely zero
descriptive content reads as coherent. Decided: this is a real defect (the
only one of the four merged findings that can produce WRONG compliance-gate
output, not just an unpinned-but-correct rule) and is fixed here, not merely
documented — see the module's own decision note in ``spec_parser.py``.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))

from lib import spec_parser  # noqa: E402


@pytest.fixture
def proj(tmp_path: Path) -> Path:
    (tmp_path / ".shipwright" / "agent_docs").mkdir(parents=True, exist_ok=True)
    return tmp_path


def _write_top_spec(proj: Path, content: str) -> None:
    (proj / ".shipwright" / "agent_docs" / "spec.md").write_text(content, encoding="utf-8")


def test_a_name_only_heading_body_has_no_description_of_its_own():
    """Sanity precondition for the next test: the HEADING body alone (no
    table involved yet) has no ``**Description:**`` — so whatever
    ``compute_fr_coherence`` reports next comes entirely from the table
    exemption, not from the heading body."""
    proj_content = (
        "| FR | Name | Priority |\n"
        "|----|------|----------|\n"
        "| FR-01.01 | User Login | Must |\n"
        "\n"
        "## FR-01.01: User Login\n"
        "**Acceptance Criteria:** works.\n"
    )
    frs = spec_parser.parse_fr_headings(proj_content)
    assert len(frs) == 1
    assert not frs[0].has_description()  # sanity: the heading body has none


def test_compute_fr_coherence_reports_missing_description_for_name_only_table(
    proj: Path,
):
    _write_top_spec(proj, (
        "| FR | Name | Priority |\n"
        "|----|------|----------|\n"
        "| FR-01.01 | User Login | Must |\n"
        "\n"
        "## FR-01.01: User Login\n"
        "**Acceptance Criteria:** works.\n"
    ))
    report = spec_parser.compute_fr_coherence(proj)
    assert any("FR-01.01" in x for x in report.missing_description)


def test_a_real_description_column_still_exempts_the_heading(proj: Path):
    """The exemption must keep working for its intended, documented case: a
    table that DOES carry a genuine Description column exempts the heading
    even though the heading's own body has none."""
    _write_top_spec(proj, (
        "| FR | Description | Priority |\n"
        "|----|-------------|----------|\n"
        "| FR-01.01 | Users can authenticate via SSO. | Must |\n"
        "\n"
        "## FR-01.01: User Login\n"
        "**Acceptance Criteria:** works.\n"
    ))
    report = spec_parser.compute_fr_coherence(proj)
    assert not any("FR-01.01" in x for x in report.missing_description)


def test_a_real_description_column_exempts_even_when_it_matches_the_name_cell(
    proj: Path,
):
    """iterate-2026-08-25-fr-criteria-parser-pin's fix compared the picked
    cell's TEXT against the Name cell's text to detect the fallback — but a
    table with a genuine, separate Description column whose content happens
    to equal its Name column's would false-negative under that heuristic
    (the two strings are equal, so it reads as "no real description" even
    though one exists). The fix is structural: ``FrTableRow.text_from_named_col``
    records whether ``text`` came from the Name column or a real title-ish
    column, so the exemption no longer depends on the two cells' content
    differing."""
    _write_top_spec(proj, (
        "| FR | Name | Description | Priority |\n"
        "|----|------|--------------|----------|\n"
        "| FR-01.01 | User Login | User Login | Must |\n"
        "\n"
        "## FR-01.01: User Login\n"
        "**Acceptance Criteria:** works.\n"
    ))
    report = spec_parser.compute_fr_coherence(proj)
    assert not any("FR-01.01" in x for x in report.missing_description)
