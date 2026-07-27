"""Tests for the shared accepted-baseline-failures reader.

``shipwright_known_failures.json`` used to be read by exactly one component
(the compliance audit). The test phase read nothing, so an onboarded project's
inherited failures were excused by one component and reported as fresh failures
by the other — two truths about one run.

These pin the ONE reader both now use
(iterate-2026-07-27-test-phase-record-honesty, FR-01.06).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from known_failures import (  # noqa: E402
    AcceptedBaseline,
    genuine_failure_count,
    load_accepted_baseline,
    split_accepted,
    within_baseline,
)
from project_facts import is_adopted_project  # noqa: E402


def _write(project: Path, payload) -> Path:
    path = project / "shipwright_known_failures.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# load_accepted_baseline — the tolerant read
# ---------------------------------------------------------------------------

@pytest.mark.covers("FR-01.06")
def test_absent_file_is_an_empty_baseline_not_an_error(tmp_path):
    baseline = load_accepted_baseline(tmp_path)
    assert baseline.present is False
    assert baseline.malformed is False
    assert baseline.entries == ()
    assert baseline.baseline_failure_count == 0


@pytest.mark.covers("FR-01.06")
def test_declared_entries_are_read_with_their_metadata(tmp_path):
    _write(tmp_path, {
        "known_failures": [
            {
                "test": "tests/test_legacy.py::test_old",
                "description": "predates onboarding",
                "ticket": "LEG-1",
                "added": "2026-01-01",
                "count": 2,
            },
            {"test": "tests/test_other.py::test_x"},
        ],
    })
    baseline = load_accepted_baseline(tmp_path)

    assert baseline.present is True
    assert [e.test for e in baseline.entries] == [
        "tests/test_legacy.py::test_old", "tests/test_other.py::test_x",
    ]
    assert baseline.entries[0].ticket == "LEG-1"
    # count defaults to 1 when the entry omits it
    assert baseline.entries[1].count == 1
    # derived from the entries when not stated explicitly
    assert baseline.baseline_failure_count == 3


@pytest.mark.covers("FR-01.06")
def test_explicit_baseline_count_wins_over_the_derived_sum(tmp_path):
    _write(tmp_path, {
        "known_failures": [{"test": "a", "count": 1}],
        "baseline_failure_count": 7,
    })
    assert load_accepted_baseline(tmp_path).baseline_failure_count == 7


@pytest.mark.covers("FR-01.06")
def test_malformed_file_is_flagged_but_yields_a_zero_baseline(tmp_path):
    (tmp_path / "shipwright_known_failures.json").write_text("{not json", encoding="utf-8")
    baseline = load_accepted_baseline(tmp_path)

    # `malformed` is the honesty signal — the caller can SAY the list was
    # unreadable instead of silently reporting "nothing is accepted".
    assert baseline.malformed is True
    assert baseline.present is True
    assert baseline.baseline_failure_count == 0
    assert baseline.entries == ()


@pytest.mark.covers("FR-01.06")
def test_a_non_object_payload_is_malformed_not_a_crash(tmp_path):
    _write(tmp_path, ["not", "an", "object"])
    assert load_accepted_baseline(tmp_path).malformed is True


@pytest.mark.covers("FR-01.06")
def test_non_list_known_failures_key_is_malformed(tmp_path):
    _write(tmp_path, {"known_failures": "oops"})
    assert load_accepted_baseline(tmp_path).malformed is True


@pytest.mark.covers("FR-01.06")
def test_garbage_entries_are_skipped_without_losing_the_good_ones(tmp_path):
    _write(tmp_path, {"known_failures": [{"test": "good"}, "junk", {"no_test_key": 1}]})
    baseline = load_accepted_baseline(tmp_path)
    assert [e.test for e in baseline.entries] == ["good"]
    assert baseline.malformed is False


@pytest.mark.covers("FR-01.06")
def test_a_non_integer_count_falls_back_to_one(tmp_path):
    _write(tmp_path, {"known_failures": [{"test": "a", "count": "three"}]})
    assert load_accepted_baseline(tmp_path).baseline_failure_count == 1


# ---------------------------------------------------------------------------
# within_baseline — the arithmetic, mirrored from rtm_generator
# ---------------------------------------------------------------------------

@pytest.mark.covers("FR-01.06")
@pytest.mark.parametrize(
    ("passed", "total", "count", "expected"),
    [
        (10, 10, 0, True),    # no gap at all
        (8, 10, 2, True),     # gap == baseline → within (rtm_generator:475-478)
        (8, 10, 1, False),    # gap > baseline → genuinely failing
        (8, 10, 0, False),    # no declared baseline → nothing is excused
        (11, 10, 0, True),    # negative gap is not a failure
    ],
)
def test_within_baseline_mirrors_the_audit_rule(passed, total, count, expected):
    assert within_baseline(passed, total, count) is expected


@pytest.mark.covers("FR-01.06")
def test_genuine_failure_count_prefers_an_explicit_failed_number(tmp_path):
    # A skipped test is NOT a failure. When the layer reports `failed`
    # explicitly, that is the honest number — never total - passed.
    assert genuine_failure_count(passed=90, total=100, failed=2, skipped=8) == 2


@pytest.mark.covers("FR-01.06")
def test_genuine_failure_count_subtracts_skips_when_failed_is_absent(tmp_path):
    assert genuine_failure_count(passed=90, total=100, failed=None, skipped=8) == 2


@pytest.mark.covers("FR-01.06")
def test_genuine_failure_count_falls_back_to_the_bare_gap(tmp_path):
    assert genuine_failure_count(passed=90, total=100, failed=None, skipped=None) == 10


@pytest.mark.covers("FR-01.06")
def test_genuine_failure_count_never_goes_negative(tmp_path):
    assert genuine_failure_count(passed=100, total=100, failed=None, skipped=5) == 0


# ---------------------------------------------------------------------------
# split_accepted — identities, not arithmetic
# ---------------------------------------------------------------------------

@pytest.mark.covers("FR-01.06")
def test_split_accepted_separates_declared_failures_from_genuine_ones(tmp_path):
    _write(tmp_path, {"known_failures": [
        {"test": "e2e/flows/01-auth.spec.ts › should login"},
    ]})
    baseline = load_accepted_baseline(tmp_path)

    accepted, genuine = split_accepted(
        ["e2e/flows/01-auth.spec.ts › should login", "checkout blows up"], baseline,
    )
    assert accepted == ["e2e/flows/01-auth.spec.ts › should login"]
    assert genuine == ["checkout blows up"]


@pytest.mark.covers("FR-01.06")
def test_split_accepted_matches_a_declared_substring_of_the_reported_name(tmp_path):
    # The declared entry is a test id; the reported failure often carries a
    # suite prefix. A declared id contained in the reported name is a match.
    _write(tmp_path, {"known_failures": [{"test": "test_old_thing"}]})
    baseline = load_accepted_baseline(tmp_path)

    accepted, genuine = split_accepted(["tests/test_legacy.py::test_old_thing"], baseline)
    assert accepted == ["tests/test_legacy.py::test_old_thing"]
    assert genuine == []


@pytest.mark.covers("FR-01.06")
def test_split_accepted_does_not_match_on_a_partial_word(tmp_path):
    _write(tmp_path, {"known_failures": [{"test": "a"}]})
    baseline = load_accepted_baseline(tmp_path)
    # A one-character declared id must not swallow every failure that
    # happens to contain that letter.
    _, genuine = split_accepted(["test_catalog_shape"], baseline)
    assert genuine == ["test_catalog_shape"]


@pytest.mark.covers("FR-01.06")
def test_a_declared_failure_that_did_not_fire_does_not_excuse_a_different_one(tmp_path):
    # External review R4: the divergent case. The declared failure is ABSENT
    # from this run and an unrelated one appeared. Counting alone would say
    # "1 failure, baseline 1, all fine". Identity matching must not.
    _write(tmp_path, {"known_failures": [{"test": "test_declared"}]})
    baseline = load_accepted_baseline(tmp_path)

    accepted, genuine = split_accepted(["test_something_new"], baseline)
    assert accepted == []
    assert genuine == ["test_something_new"]


@pytest.mark.covers("FR-01.06")
def test_split_accepted_with_no_baseline_calls_everything_genuine(tmp_path):
    accepted, genuine = split_accepted(["a", "b"], load_accepted_baseline(tmp_path))
    assert accepted == []
    assert genuine == ["a", "b"]


@pytest.mark.covers("FR-01.06")
def test_split_accepted_tolerates_non_string_failure_names(tmp_path):
    baseline = AcceptedBaseline(entries=(), baseline_failure_count=0,
                                present=False, malformed=False)
    accepted, genuine = split_accepted([None, 42, "real"], baseline)  # type: ignore[list-item]
    assert accepted == []
    assert genuine == ["real"]


# ---------------------------------------------------------------------------
# project_facts.is_adopted_project — the greenfield / brownfield signal
# ---------------------------------------------------------------------------

@pytest.mark.covers("FR-01.06")
def test_a_project_with_an_adoption_block_is_brownfield(tmp_path):
    (tmp_path / "shipwright_run_config.json").write_text(
        json.dumps({"adoption": {"adopted_at": "2026-01-01", "commit_at_adoption": "abc"}}),
        encoding="utf-8",
    )
    assert is_adopted_project(tmp_path) is True


@pytest.mark.covers("FR-01.06")
def test_an_empty_adoption_block_is_not_adoption(tmp_path):
    (tmp_path / "shipwright_run_config.json").write_text(
        json.dumps({"adoption": {}}), encoding="utf-8")
    assert is_adopted_project(tmp_path) is False


@pytest.mark.covers("FR-01.06")
def test_scope_is_not_the_adoption_signal(tmp_path):
    # Iterate B.1 chose `adoption` over `scope` empirically — `scope` carries
    # "library" / "full_app", orthogonal to how the project was onboarded.
    (tmp_path / "shipwright_run_config.json").write_text(
        json.dumps({"scope": "library"}), encoding="utf-8")
    assert is_adopted_project(tmp_path) is False


@pytest.mark.covers("FR-01.06")
def test_a_missing_or_broken_run_config_reads_as_greenfield(tmp_path):
    assert is_adopted_project(tmp_path) is False
    (tmp_path / "shipwright_run_config.json").write_text("{broken", encoding="utf-8")
    assert is_adopted_project(tmp_path) is False
