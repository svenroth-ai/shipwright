"""Tests for shared/scripts/tools/verifiers/design_screens_parser.py.

Also covers the ``## Non-UI FRs`` exemption in
``design_checks.check_design_fr_coverage`` (integration-level, since the
exemption only has an observable effect through that check).
"""

from __future__ import annotations

from tools.verifiers.design_checks import check_design_fr_coverage
from tools.verifiers.design_screens_parser import (
    parse_non_ui_frs,
    parse_screens_table,
    summarize_fr_coverage,
)

from .test_verifiers_design import seed_canon_design

# ---------------------------------------------------------------------------
# parse_screens_table
# ---------------------------------------------------------------------------


def test_parse_screens_table_extracts_file_and_frs():
    md = (
        "## Screens\n\n"
        "| # | Screen | File | Status | Linked FRs |\n"
        "|---|--------|------|--------|-----------|\n"
        "| 01 | Login | screens/01-login.html | complete | FR-01.01, FR-01.02 |\n"
        "| 02 | Dashboard | screens/02-dashboard.html | complete | FR-02.01 |\n"
        "\n## User Flows\n"
    )
    rows = parse_screens_table(md)
    assert len(rows) == 2
    assert rows[0][0] == "screens/01-login.html"
    assert set(rows[0][1]) == {"FR-01.01", "FR-01.02"}
    assert rows[1][1] == ["FR-02.01"]


def test_parse_screens_table_treats_none_as_empty_fr_list():
    md = (
        "## Screens\n\n"
        "| # | Screen | File | Status | Linked FRs |\n"
        "|---|--------|------|--------|-----------|\n"
        "| 01 | Logo | screens/logo.html | complete | none |\n"
    )
    rows = parse_screens_table(md)
    assert rows == [("screens/logo.html", [])]


def test_parse_screens_table_stops_at_next_section():
    md = (
        "## Screens\n\n"
        "| # | Screen | File | Status | Linked FRs |\n"
        "|---|--------|------|--------|-----------|\n"
        "| 01 | A | screens/a.html | complete | FR-01.01 |\n"
        "\n## User Flows\n\n"
        "| Flow | File | Screens | Status |\n"
        "| Auth | flows/auth.html | 01 -> 02 | complete |\n"
    )
    rows = parse_screens_table(md)
    # Only the Screens row is returned — User Flows rows are ignored
    assert len(rows) == 1
    assert rows[0][0] == "screens/a.html"


def test_parse_screens_table_tolerates_extra_column():
    """Regression: a 6-column table (extra "Split" column distinguishing
    frontend/backend screens) must still parse — a position-anchored
    5-column regex previously zeroed out ALL rows here."""
    md = (
        "## Screens\n\n"
        "| # | Screen | File | Split | Status | Linked FRs |\n"
        "|---|--------|------|-------|--------|-----------|\n"
        "| 01 | Login | screens/01-login.html | frontend | complete | FR-01.01 |\n"
        "| 02 | Job | screens/02-job.html | backend | complete | FR-02.01, FR-02.02 |\n"
    )
    rows = parse_screens_table(md)
    assert len(rows) == 2
    assert rows[0] == ("screens/01-login.html", ["FR-01.01"])
    assert rows[1] == ("screens/02-job.html", ["FR-02.01", "FR-02.02"])


def test_parse_screens_table_prefers_linked_frs_over_ambiguous_earlier_fr_column():
    """Regression: an extended table with an earlier column mentioning "FR"
    (e.g. "FR Status") must not shadow the real "Linked FRs" column — the
    first bare-FR match would otherwise win and extract nothing."""
    md = (
        "## Screens\n\n"
        "| # | Screen | File | FR Status | Status | Linked FRs |\n"
        "|---|--------|------|-----------|--------|-----------|\n"
        "| 01 | Login | screens/01-login.html | reviewed | complete | FR-01.01 |\n"
    )
    rows = parse_screens_table(md)
    assert rows == [("screens/01-login.html", ["FR-01.01"])]


def test_parse_screens_table_linked_frs_matcher_ignores_unlinked_column():
    """Regression: "Unlinked FRs" contains "linked" as a substring — the
    linked-FRs matcher must not fire on it, or it would shadow the real
    "Linked FRs" column when it appears earlier in the header row."""
    md = (
        "## Screens\n\n"
        "| # | Screen | File | Unlinked FRs | Status | Linked FRs |\n"
        "|---|--------|------|---------------|--------|-----------|\n"
        "| 01 | Login | screens/01-login.html | FR-99.99 | complete | FR-01.01 |\n"
    )
    rows = parse_screens_table(md)
    assert rows == [("screens/01-login.html", ["FR-01.01"])]


def test_parse_screens_table_header_matchers_are_whole_word():
    """Regression: an unrelated header containing "fr"/"file" as a
    substring (not a whole word) must not be picked as the file/FR column."""
    md = (
        "## Screens\n\n"
        "| # | Screen | Frame | File | Status | Linked FRs |\n"
        "|---|--------|-------|------|--------|-----------|\n"
        "| 01 | Login | outer | screens/01-login.html | complete | FR-01.01 |\n"
    )
    rows = parse_screens_table(md)
    assert rows == [("screens/01-login.html", ["FR-01.01"])]


def test_parse_screens_table_returns_empty_for_headerless_table():
    """Intentional: header-name lookup requires a header row naming the
    File/FR columns. A table with only a separator row and data (no header)
    parses to nothing rather than guessing column positions."""
    md = "## Screens\n\n|---|---|---|---|---|\n| 01 | Logo | screens/logo.html | complete | none |\n"
    assert parse_screens_table(md) == []


def test_parse_screens_table_returns_empty_when_no_screens_section():
    assert parse_screens_table("## User Flows\n") == []


def test_parse_screens_table_stops_at_blank_line_before_subheading():
    """Regression: a "### " subheading does not end the ## Screens section
    (only "## " does), so a second unrelated table under it must not be
    merged into the first using the first table's column indices."""
    md = (
        "## Screens\n\n"
        "| # | Screen | File | Status | Linked FRs |\n"
        "|---|--------|------|--------|-----------|\n"
        "| 01 | A | screens/a.html | complete | FR-01.01 |\n"
        "\n### Archived screens\n\n"
        "| Name | Removed |\n"
        "|------|---------|\n"
        "| Old | 2026-01-01 |\n"
    )
    rows = parse_screens_table(md)
    assert rows == [("screens/a.html", ["FR-01.01"])]


# ---------------------------------------------------------------------------
# parse_non_ui_frs
# ---------------------------------------------------------------------------


def test_parse_non_ui_frs_returns_ids_from_section():
    md = (
        "## Non-UI FRs\n\n"
        "- FR-03.01 — ADR-004 (background job, no screen)\n"
        "- FR-05.02 — ADR-010\n"
        "\n## Screens\n"
    )
    assert parse_non_ui_frs(md) == {"FR-03.01", "FR-05.02"}


def test_parse_non_ui_frs_empty_when_section_absent():
    assert parse_non_ui_frs("## Screens\n") == set()


def test_parse_non_ui_frs_ignores_entry_without_adr_reference():
    """An exemption of an ERROR-severity gate must always leave an
    auditable trail — a line with no ADR-NNN reference is not exempted."""
    md = "## Non-UI FRs\n\n- FR-03.01 (background job, no screen, no ADR cited)\n"
    assert parse_non_ui_frs(md) == set()


# ---------------------------------------------------------------------------
# summarize_fr_coverage
# ---------------------------------------------------------------------------


def test_summarize_fr_coverage_distinguishes_parse_failure_from_orphans():
    """When the Screens table cannot be parsed at all, the detail must say
    so instead of blaming every declared FR individually."""
    ok, detail = summarize_fr_coverage({"FR-01.01"}, rows=[], non_ui=set())
    assert ok is False
    assert "no Screens rows parsed" in detail


def test_summarize_fr_coverage_flags_unparsed_table_even_when_fully_exempt():
    """A Screens table that fails to parse must not go silently unnoticed
    just because every declared FR happens to be Non-UI-exempt."""
    ok, detail = summarize_fr_coverage({"FR-01.01"}, rows=[], non_ui={"FR-01.01"})
    assert ok is True
    assert "no Screens rows parsed" in detail


def test_summarize_fr_coverage_reports_stale_non_ui_entries_even_when_orphans_exist():
    """A misspelled Non-UI FR id must not go unnoticed just because a
    genuine orphan is already failing the check for a different reason."""
    ok, detail = summarize_fr_coverage(
        {"FR-01.01", "FR-02.02"},
        rows=[("screens/a.html", ["FR-01.01"])],
        non_ui={"FR-99.99"},
    )
    assert ok is False
    assert "FR-02.02" in detail
    assert "Non-UI FR entry(ies) match no declared FR" in detail
    assert "FR-99.99" in detail


def test_summarize_fr_coverage_reports_stale_non_ui_entries():
    ok, detail = summarize_fr_coverage(
        {"FR-01.01"}, rows=[("screens/a.html", ["FR-01.01"])], non_ui={"FR-99.99"}
    )
    assert ok is True
    assert "1 Non-UI FR entry(ies) match no declared FR" in detail
    assert "FR-99.99" in detail


# ---------------------------------------------------------------------------
# check_design_fr_coverage — Non-UI FR exemption
# ---------------------------------------------------------------------------


def test_fr_coverage_exempts_fr_listed_as_non_ui(tmp_path):
    seed_canon_design(tmp_path)
    # Declare a third FR that has no screen — genuinely backend-only.
    (tmp_path / ".shipwright" / "planning" / "02-dashboard" / "spec.md").write_text(
        "| ID | Requirement | Priority |\n"
        "| FR-02.01 | Show metrics | Must |\n"
        "| FR-02.02 | Export PDF (backend job) | Should |\n"
    )
    manifest = tmp_path / ".shipwright" / "designs" / "design-manifest.md"
    manifest.write_text(
        manifest.read_text() + "\n## Non-UI FRs\n\n- FR-02.02 — ADR-004 (backend job)\n"
    )
    r = check_design_fr_coverage(tmp_path)
    assert r.ok is True
    assert "1 exempt as Non-UI FRs" in r.detail


def test_fr_coverage_still_fails_when_fr_not_listed_as_non_ui(tmp_path):
    """Same setup as above minus the exemption — proves the exemption test
    above is discriminating (an unmarked orphan still fails)."""
    seed_canon_design(tmp_path)
    (tmp_path / ".shipwright" / "planning" / "02-dashboard" / "spec.md").write_text(
        "| ID | Requirement | Priority |\n"
        "| FR-02.01 | Show metrics | Must |\n"
        "| FR-02.02 | Export PDF (backend job) | Should |\n"
    )
    r = check_design_fr_coverage(tmp_path)
    assert r.ok is False
    assert "FR-02.02" in r.detail
