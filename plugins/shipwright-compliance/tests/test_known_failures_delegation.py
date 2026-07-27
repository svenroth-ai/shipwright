"""The audit collector delegates the accepted-baseline read; behaviour is unchanged.

``collect_known_failures`` used to own the only parse of
``shipwright_known_failures.json``. The test phase now reads the same list, so
the parse moved to ``shared/scripts/known_failures.py`` and this collector
became a thin adapter over it.

The point of the move is that the two components cannot hold different truths
about one run — which only holds if the audit's observable behaviour did not
shift when it started delegating. These tests pin exactly that: signature,
return types, and the answer for present / absent / malformed / partial input.

iterate-2026-07-27-test-phase-record-honesty, FR-01.06.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.lib.collectors import collect_known_failures
from scripts.lib.collectors._types import KnownFailure


def _write(project: Path, payload: object) -> None:
    (project / "shipwright_known_failures.json").write_text(
        json.dumps(payload), encoding="utf-8")


@pytest.mark.covers("FR-01.06")
def test_absent_file_still_yields_empty_list_and_zero_baseline(tmp_path: Path):
    assert collect_known_failures(tmp_path) == ([], 0)


@pytest.mark.covers("FR-01.06")
def test_malformed_file_still_yields_empty_list_and_zero_baseline(tmp_path: Path):
    (tmp_path / "shipwright_known_failures.json").write_text("{nope", encoding="utf-8")
    assert collect_known_failures(tmp_path) == ([], 0)


@pytest.mark.covers("FR-01.06")
def test_entries_are_returned_as_KnownFailure_with_the_same_fields(tmp_path: Path):
    _write(tmp_path, {"known_failures": [
        {
            "test": "tests/test_legacy.py::test_old",
            "description": "predates adoption",
            "ticket": "LEG-1",
            "added": "2026-01-01",
            "count": 2,
        },
    ]})
    failures, baseline = collect_known_failures(tmp_path)

    assert baseline == 2
    assert len(failures) == 1
    entry = failures[0]
    # The dataclass identity matters — the RTM and dashboard render these.
    assert isinstance(entry, KnownFailure)
    assert entry.test == "tests/test_legacy.py::test_old"
    assert entry.description == "predates adoption"
    assert entry.ticket == "LEG-1"
    assert entry.added == "2026-01-01"
    assert entry.count == 2


@pytest.mark.covers("FR-01.06")
def test_missing_optional_fields_default_exactly_as_before(tmp_path: Path):
    _write(tmp_path, {"known_failures": [{"test": "a"}]})
    failures, baseline = collect_known_failures(tmp_path)

    assert baseline == 1
    assert (failures[0].description, failures[0].ticket, failures[0].added) == ("", "", "")
    assert failures[0].count == 1


@pytest.mark.covers("FR-01.06")
def test_explicit_baseline_count_still_wins(tmp_path: Path):
    _write(tmp_path, {"known_failures": [{"test": "a"}], "baseline_failure_count": 5})
    assert collect_known_failures(tmp_path)[1] == 5


@pytest.mark.covers("FR-01.06")
def test_empty_known_failures_list_is_a_present_but_empty_baseline(tmp_path: Path):
    _write(tmp_path, {"known_failures": []})
    assert collect_known_failures(tmp_path) == ([], 0)


@pytest.mark.covers("FR-01.06")
def test_the_audit_and_the_test_phase_read_one_parser(tmp_path: Path):
    """AC5 — the same file, read once, giving both sides the same answer."""
    import sys

    shared_scripts = Path(__file__).resolve().parents[3] / "shared" / "scripts"
    if str(shared_scripts) not in sys.path:
        sys.path.insert(0, str(shared_scripts))
    from known_failures import load_accepted_baseline

    _write(tmp_path, {"known_failures": [
        {"test": "test_a", "count": 2}, {"test": "test_b"},
    ]})

    audit_failures, audit_baseline = collect_known_failures(tmp_path)
    shared_view = load_accepted_baseline(tmp_path)

    assert audit_baseline == shared_view.baseline_failure_count == 3
    assert [f.test for f in audit_failures] == [e.test for e in shared_view.entries]
