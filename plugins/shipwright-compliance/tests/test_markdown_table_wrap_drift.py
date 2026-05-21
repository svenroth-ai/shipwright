"""Drift-protection for the markdown_table.escape_cell wraps.

Promoted from the one-shot empirical probe used during
iterate-2026-05-20-escape-md-cells to verify that pipe-laden event
fields land in compliance markdown tables in their escaped form
(`\\|`) — never raw `|`. If a future iterate silently removes a
wrap from one of the five rendered files, this parametrized test
fails for that generator+field pair.

The test feeds a synthetic ComplianceData with pipe-laden inputs
through each generator, then asserts:

  * The full ESCAPED needle appears in some data row.
  * The full RAW needle does NOT appear in any data row.

The needle is anchored at a prefix unique to the test fixture
(e.g. ``ZZZ_drift_``), so it cannot false-match a heading or
neighbouring row's content.

Origin: iterate-2026-05-21-post-43-hygiene
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from scripts.lib.change_history import generate as generate_change_history
from scripts.lib.compliance_report import generate as generate_compliance_report
from scripts.lib.data_collector import (
    CommitEntry,
    ComplianceData,
    ExternalReviewState,
    WorkEvent,
)
from scripts.lib.rtm_generator import generate as generate_rtm
from scripts.lib.test_evidence import generate as generate_test_evidence

# Needle prefix chosen to be unique against heading text + neighbour rows.
_NEEDLE_PREFIX = "ZZZ_drift_"


def _table_data_rows(md: str) -> list[str]:
    """Yield only the data rows of markdown tables (skip header + separator)."""
    rows: list[str] = []
    in_table = False
    expecting_separator = False
    for line in md.splitlines():
        if line.startswith("|"):
            if not in_table:
                in_table = True
                expecting_separator = True
                continue
            if expecting_separator and set(line) <= set("|-: "):
                expecting_separator = False
                continue
            rows.append(line)
        else:
            in_table = False
            expecting_separator = False
    return rows


def _assert_escaped(md: str, needle_with_pipe: str) -> None:
    """Assert the needle appears in some row, only ever in its escaped form."""
    escaped = needle_with_pipe.replace("|", "\\|")
    rows = _table_data_rows(md)

    # Must appear somewhere in escaped form
    matching = [r for r in rows if escaped in r]
    assert matching, (
        f"Escaped needle '{escaped}' not found in any markdown data row.\n"
        f"Rows containing prefix '{_NEEDLE_PREFIX}':\n  "
        + "\n  ".join(r for r in rows if _NEEDLE_PREFIX in r)
    )

    # Must NEVER appear in raw form (un-escaped pipe in the needle's span)
    for row in rows:
        if needle_with_pipe in row and escaped not in row:
            pytest.fail(
                f"Row contains UNESCAPED needle '{needle_with_pipe}' — wrap missing.\n"
                f"  row: {row!r}"
            )


def _minimal_data() -> ComplianceData:
    d = ComplianceData(project_root=Path("."))
    d.timestamp = "2026-05-21T00:00:00Z"
    return d


def _work_event(*, description: str, source: str = "iterate") -> WorkEvent:
    return WorkEvent(
        id="evt-drift",
        timestamp="2026-05-21T10:00:00+00:00",
        source=source,
        commit="deadbee",
        tests_passed=1,
        tests_total=1,
        affected_frs=[],
        split="",
        section="",
        review_type="self-review",
        review_findings=0,
        review_fixed=0,
        intent="change",
        description=description,
        new_frs=[],
        tests_new=0,
        tests_modified=0,
        e2e_run=False,
        spec_updated="",
        adr_id="",
    )


# ---------------------------------------------------------------------------
# Each parameter case names ONE generator + ONE event-derived cell that the
# escape_cell wrap protects. The needle carries `_NEEDLE_PREFIX` plus literal
# `|` characters; the test asserts that whichever row exposes that cell
# renders the pipes as `\|`.
# ---------------------------------------------------------------------------

_NEEDLE_COMMIT_DESC = f"{_NEEDLE_PREFIX}commit|with|pipes"
_NEEDLE_WORK_DESC = f"{_NEEDLE_PREFIX}work|with|pipes"
_NEEDLE_EXT_PROVIDER = f"{_NEEDLE_PREFIX}openai|gemini"
_NEEDLE_EXT_REASON = f"{_NEEDLE_PREFIX}2 HIGH | 1 MED | 2 LOW"


def _case_change_history():
    """change_history.py — commits-by-type row, `description` field."""
    d = _minimal_data()
    d.commits = [
        CommitEntry(
            hash="abc1234",
            type="feat",
            scope="auth",
            description=_NEEDLE_COMMIT_DESC,
            date="2026-05-21T10:00:00+00:00",
            author="Claude",
        ),
    ]
    return generate_change_history(d), _NEEDLE_COMMIT_DESC


def _case_rtm_verification_timeline():
    """rtm_generator.py — _verification_timeline row, `description` field."""
    d = _minimal_data()
    d.work_events = [_work_event(description=_NEEDLE_WORK_DESC)]
    return generate_rtm(d), _NEEDLE_WORK_DESC


def _case_test_evidence_progression():
    """test_evidence.py — _test_progression row, `description` field."""
    d = _minimal_data()
    d.work_events = [_work_event(description=_NEEDLE_WORK_DESC)]
    return generate_test_evidence(d), _NEEDLE_WORK_DESC


def _case_compliance_report_provider():
    """compliance_report.py — _external_review_evidence row, `provider` field."""
    d = _minimal_data()
    d.external_review_states = [
        ExternalReviewState(
            split="01-foundation",
            status="completed",
            provider=_NEEDLE_EXT_PROVIDER,
            findings_count=5,
            self_review_fallback_ran=False,
            reason="—",
        ),
    ]
    return generate_compliance_report(d), _NEEDLE_EXT_PROVIDER


def _case_compliance_report_reason():
    """compliance_report.py — _external_review_evidence row, `reason` field."""
    d = _minimal_data()
    d.external_review_states = [
        ExternalReviewState(
            split="01-foundation",
            status="completed",
            provider="openrouter",
            findings_count=5,
            self_review_fallback_ran=False,
            reason=_NEEDLE_EXT_REASON,
        ),
    ]
    return generate_compliance_report(d), _NEEDLE_EXT_REASON


_CASES = {
    "change_history.description": _case_change_history,
    "rtm.verification_timeline.description": _case_rtm_verification_timeline,
    "test_evidence.test_progression.description": _case_test_evidence_progression,
    "compliance_report.external_review.provider": _case_compliance_report_provider,
    "compliance_report.external_review.reason": _case_compliance_report_reason,
}


@pytest.mark.parametrize("case_id", list(_CASES.keys()))
def test_event_derived_cells_escape_pipe(case_id: str) -> None:
    """Each event-derived cell that takes free-text from event data must
    render its content with `|` escaped as `\\|`. If a future iterate
    silently un-wraps one of these cells, this test fails for that
    generator+field pair.
    """
    rendered_md, needle = _CASES[case_id]()
    _assert_escaped(rendered_md, needle)


def test_newline_in_event_field_collapses_to_space() -> None:
    """Defence-in-depth: a newline in an event field must collapse to a
    single space (escape_cell guarantee). Asserts the row stays on one
    physical line in the rendered markdown.
    """
    d = _minimal_data()
    d.work_events = [
        _work_event(description=f"{_NEEDLE_PREFIX}line1\nline2"),
    ]
    md = generate_test_evidence(d)
    matching = [r for r in _table_data_rows(md) if _NEEDLE_PREFIX in r]
    assert matching, "synthetic event not rendered in any data row"
    # At least one row must show the collapsed form (newline → space).
    collapsed_rows = [r for r in matching if f"{_NEEDLE_PREFIX}line1 line2" in r]
    assert collapsed_rows, (
        f"newline should have collapsed to a single space in the description cell "
        f"— rows containing prefix:\n  " + "\n  ".join(matching)
    )
    # And no matching row may carry a literal embedded newline.
    for row in matching:
        assert "\n" not in row, f"row contains a literal newline: {row!r}"
