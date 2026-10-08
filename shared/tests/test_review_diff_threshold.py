"""The one definition of the review diff-size trigger (``lib/review_diff_threshold.py``)."""

from __future__ import annotations

import pytest

from lib import review_diff_threshold as rdt


@pytest.mark.covers("FR-01.11")
def test_boundary_is_strictly_greater_than_100():
    assert rdt.DIFF_LOC_THRESHOLD == rdt.PLAN_REVIEW_DIFF_LOC_THRESHOLD == 100
    assert rdt.exceeds_diff_threshold(100) is False
    assert rdt.exceeds_diff_threshold(101) is True


@pytest.mark.covers("FR-01.11")
def test_numstat_counts_added_plus_removed_and_binary_as_zero():
    raw = "3\t4\tsrc/a.py\n-\t-\tlogo.png\n10\t0\tdocs/x.md\n"
    paths, total = rdt.numstat_changed_lines(raw)
    assert paths == ["src/a.py", "logo.png", "docs/x.md"]
    assert total == 17


@pytest.mark.covers("FR-01.11")
def test_numstat_accepts_nul_separated_records():
    assert rdt.numstat_changed_lines("1\t1\ta.py\0002\t0\tb.py\0")[1] == 4


@pytest.mark.covers("FR-01.11")
def test_a_newline_inside_a_nul_separated_path_is_data():
    paths, total = rdt.numstat_changed_lines("1\t0\tsrc/a\nb.py\0")
    assert paths == ["src/a\nb.py"] and total == 1


@pytest.mark.covers("FR-01.11")
def test_finalization_records_are_listed_but_not_counted():
    raw = ("50\t0\t.shipwright/agent_docs/iterates/x.json\n"
           "9\t0\tCHANGELOG-unreleased.d/added/x.md\n"
           "7\t1\tshipwright_events.jsonl\n"
           "4\t4\tshipwright_test_results.json\n"
           "2\t0\tsrc/a.py\n")
    paths, total = rdt.numstat_changed_lines(raw)
    assert len(paths) == 5 and total == 2


@pytest.mark.covers("FR-01.11")
@pytest.mark.parametrize("path,counted", [
    (".shipwright/planning/iterate/x/spec.md", False),
    ("./.shipwright/x.json", False),
    ("shared/scripts/lib/a.py", True),
    ("docs/shipwright_events.jsonl", True),
    ("", False),
])
def test_is_counted_path(path, counted):
    assert rdt.is_counted_path(path) is counted


@pytest.mark.covers("FR-01.11")
def test_a_rename_record_raises():
    with pytest.raises(ValueError, match="rename"):
        rdt.numstat_changed_lines("1\t0\t\n")
