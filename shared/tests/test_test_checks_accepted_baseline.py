"""The test-phase validator reads the same accepted-baseline list the audit reads.

Before this, ``check_test_results_file_fresh`` compared ``unit.passed`` against
``unit.total`` and knew nothing about ``shipwright_known_failures.json``. On an
onboarded project that meant a permanently WARNING test phase while the audit
reported the same run as within baseline — two components, two truths.

It also read every passed<total gap as failures, so a run with host-gated
*skips* consumed accepted-failure allowance it never should have.

iterate-2026-07-27-test-phase-record-honesty, FR-01.06.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.verifiers.common import Severity
from tools.verifiers.test_checks import check_test_results_file_fresh


def _results(root: Path, unit: dict) -> None:
    (root / "shipwright_test_results.json").write_text(
        json.dumps({"unit": unit}), encoding="utf-8")


def _baseline(root: Path, payload: dict) -> None:
    (root / "shipwright_known_failures.json").write_text(
        json.dumps(payload), encoding="utf-8")


# ---------------------------------------------------------------------------
# Unchanged behaviour — no declared baseline means nothing is excused
# ---------------------------------------------------------------------------

@pytest.mark.covers("FR-01.06")
def test_a_gap_with_no_declared_baseline_still_warns(tmp_path: Path):
    _results(tmp_path, {"passed": 3, "total": 5})
    r = check_test_results_file_fresh(tmp_path)
    assert r.ok is False
    assert r.severity == Severity.WARNING.value


@pytest.mark.covers("FR-01.06")
def test_a_green_run_still_passes(tmp_path: Path):
    _results(tmp_path, {"passed": 10, "total": 10})
    assert check_test_results_file_fresh(tmp_path).ok is True


@pytest.mark.covers("FR-01.06")
def test_an_empty_run_is_still_never_a_pass(tmp_path: Path):
    _results(tmp_path, {"passed": 0, "total": 0})
    r = check_test_results_file_fresh(tmp_path)
    assert r.ok is False
    assert r.severity == Severity.ERROR.value


# ---------------------------------------------------------------------------
# AC4 — accepted baseline failures are not reported as a failing run
# ---------------------------------------------------------------------------

@pytest.mark.covers("FR-01.06")
def test_an_unbroken_gap_within_the_declared_baseline_does_not_fail_the_check(tmp_path: Path):
    """The card's motivating case: an onboarded project reporting bare counts.

    No `failed` / `skipped` breakdown, so all we have is a gap — the audit reads
    that charitably against the declared baseline, and so must this.
    """
    _results(tmp_path, {"passed": 828, "total": 830})
    _baseline(tmp_path, {"known_failures": [
        {"test": "test_a"}, {"test": "test_b"},
    ]})
    r = check_test_results_file_fresh(tmp_path)

    assert r.ok is True
    # And it SAYS so — an operator must be able to tell "within baseline"
    # from "everything passed".
    assert "baseline" in r.detail.lower()
    assert "2" in r.detail
    # ...and it does not overclaim: the allowance is aggregate, not per-failure.
    assert "aggregate allowance" in r.detail


@pytest.mark.covers("FR-01.06")
def test_an_exactly_counted_failure_is_not_waived_by_the_baseline(tmp_path: Path):
    """The audit made this call deliberately; the test phase must match it.

    `tests_block.progression_result` renders FAIL for an explicit residual even
    when the baseline would cover it — pinned compliance-side by
    `test_explicit_residual_ignores_baseline_charity`, because the D4 detective
    keys on genuine failures and a PASS (baseline) render would contradict it.
    Waiving an exactly-counted failure on a count is precisely the dishonest
    green this iterate exists to remove.
    """
    _results(tmp_path, {"passed": 828, "total": 830, "failed": 2})
    _baseline(tmp_path, {"known_failures": [{"test": "test_a"}, {"test": "test_b"}]})
    r = check_test_results_file_fresh(tmp_path)

    assert r.ok is False
    assert r.severity == Severity.WARNING.value
    assert "2 failing" in r.detail
    assert "declared in the baseline" in r.detail
    # It points at the honest resolution rather than at arithmetic.
    assert "by name" in r.detail


@pytest.mark.covers("FR-01.06")
def test_a_gap_beyond_the_baseline_still_warns_and_names_both_numbers(tmp_path: Path):
    _results(tmp_path, {"passed": 827, "total": 830})
    _baseline(tmp_path, {"known_failures": [{"test": "a"}, {"test": "b"}]})
    r = check_test_results_file_fresh(tmp_path)

    assert r.ok is False
    assert r.severity == Severity.WARNING.value
    # The whole point of the card: genuine failures must not hide inside a
    # single red number.
    assert "3" in r.detail and "2" in r.detail


@pytest.mark.covers("FR-01.06")
def test_an_unreadable_baseline_file_never_widens_what_is_excused(tmp_path: Path):
    _results(tmp_path, {"passed": 3, "total": 5, "failed": 2})
    (tmp_path / "shipwright_known_failures.json").write_text("{broken", encoding="utf-8")
    r = check_test_results_file_fresh(tmp_path)

    assert r.ok is False
    # ...and it says the list could not be read, rather than silently
    # reporting "nothing is accepted".
    assert "unreadable" in r.detail.lower() or "malformed" in r.detail.lower()


# ---------------------------------------------------------------------------
# External review R3 — skips are not failures
# ---------------------------------------------------------------------------

@pytest.mark.covers("FR-01.06")
def test_an_explicit_failed_count_is_preferred_over_the_bare_gap(tmp_path: Path):
    # 10 of the gap are skips, 0 are failures. Nothing is wrong with this run.
    _results(tmp_path, {"passed": 90, "total": 100, "failed": 0, "skipped": 10})
    assert check_test_results_file_fresh(tmp_path).ok is True


@pytest.mark.covers("FR-01.06")
def test_skips_are_subtracted_when_no_failed_count_is_recorded(tmp_path: Path):
    _results(tmp_path, {"passed": 90, "total": 100, "skipped": 10})
    assert check_test_results_file_fresh(tmp_path).ok is True


@pytest.mark.covers("FR-01.06")
def test_skips_plus_a_real_failure_still_warns(tmp_path: Path):
    _results(tmp_path, {"passed": 90, "total": 100, "failed": 1, "skipped": 9})
    r = check_test_results_file_fresh(tmp_path)
    assert r.ok is False
    assert r.severity == Severity.WARNING.value


@pytest.mark.covers("FR-01.06")
def test_a_skip_only_gap_does_not_consume_accepted_failure_allowance(tmp_path: Path):
    # Baseline of 1 exists, but the run has 5 skips and 0 failures. The
    # allowance must be left untouched — and the check must pass.
    _results(tmp_path, {"passed": 95, "total": 100, "skipped": 5})
    _baseline(tmp_path, {"known_failures": [{"test": "a"}]})
    r = check_test_results_file_fresh(tmp_path)
    assert r.ok is True
    assert "baseline" not in r.detail.lower()


@pytest.mark.covers("FR-01.06")
def test_an_explicit_skip_count_also_makes_the_residual_exact(tmp_path: Path):
    # `skipped` alone pins the residual, so the allowance does not apply here
    # either — same rule, same reason.
    _results(tmp_path, {"passed": 90, "total": 100, "skipped": 8})
    _baseline(tmp_path, {"known_failures": [{"test": "a"}, {"test": "b"}]})
    r = check_test_results_file_fresh(tmp_path)

    assert r.ok is False
    assert "2 failing" in r.detail


@pytest.mark.covers("FR-01.06")
def test_a_malformed_results_file_is_still_an_error(tmp_path: Path):
    (tmp_path / "shipwright_test_results.json").write_text("{nope", encoding="utf-8")
    r = check_test_results_file_fresh(tmp_path)
    assert r.ok is False
    assert r.severity == Severity.ERROR.value


@pytest.mark.covers("FR-01.06")
def test_a_non_integer_failed_field_falls_back_rather_than_crashing(tmp_path: Path):
    _results(tmp_path, {"passed": 3, "total": 5, "failed": "two"})
    r = check_test_results_file_fresh(tmp_path)
    assert r.ok is False
    assert r.severity == Severity.WARNING.value
