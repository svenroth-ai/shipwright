"""The test phase and the audit must not disagree about what counts as failing.

Two pieces of arithmetic answer the same question from different sides:

* ``tests_block.progression_result`` — what the AUDIT renders in the Test
  Progression cell (a string: PASS / PASS (baseline) / FAIL (n failed, ...)).
* ``known_failures.genuine_failure_count`` + ``within_baseline`` — what the TEST
  PHASE validator decides (a verdict: is this run failing?).

One returns a cell, the other a number, so neither can call the other. This
pins their agreement instead: for the same inputs, the audit's PASS/FAIL and
the test phase's ok/not-ok must match.

Caught by external code review, which flagged the validator as diverging from
the audit's rule. It does not — but nothing was stopping it from drifting there
later, and "two components hold different truths about one run" is the exact
defect iterate-2026-07-27-test-phase-record-honesty exists to close. FR-01.06.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from known_failures import (  # noqa: E402
    genuine_failure_count,
    has_exact_failure_count,
    within_baseline,
)
from tests_block import progression_result  # noqa: E402


def _audit_says_failing(passed: int, total: int, skipped, baseline: int) -> bool:
    return progression_result(passed, total, skipped, baseline).startswith("FAIL")


def _test_phase_says_failing(
    passed: int, total: int, skipped, baseline: int, failed=None,
) -> bool:
    """The validator's decision, reduced to a boolean (see ``test_checks``)."""
    exact = has_exact_failure_count(failed, skipped)
    genuine = genuine_failure_count(
        passed=passed, total=total, failed=failed,
        skipped=skipped if isinstance(skipped, int) else None,
    )
    if genuine <= 0:
        return False
    # The aggregate allowance is charity for an un-broken-down gap only.
    return exact or not (baseline > 0 and genuine <= baseline)


@pytest.mark.covers("FR-01.06")
@pytest.mark.parametrize(
    ("passed", "total", "skipped", "baseline"),
    [
        (10, 10, None, 0),      # clean run, no skip field
        (10, 10, 0, 0),         # clean run, explicit zero skips
        (90, 100, 10, 0),       # gap is entirely skips
        (90, 100, 10, 1),       # ...and a baseline exists but is untouched
        (90, 100, 9, 0),        # 9 skips + 1 genuine failure
        (90, 100, 0, 0),        # 10 genuine failures
        (95, 100, 5, 5),        # skips equal to the baseline — still not failures
        (100, 100, 5, 0),       # more passes than the gap allows; never negative
        (0, 0, None, 0),        # nothing ran
        (0, 10, 0, 0),          # everything failed
    ],
)
def test_the_audit_and_the_test_phase_agree_on_failing(passed, total, skipped, baseline):
    assert _audit_says_failing(passed, total, skipped, baseline) == \
        _test_phase_says_failing(passed, total, skipped, baseline)


@pytest.mark.covers("FR-01.06")
@pytest.mark.parametrize(
    ("passed", "total", "baseline"),
    [(8, 10, 2), (8, 10, 3), (9, 10, 1), (828, 830, 2)],
)
def test_a_gap_the_declared_baseline_covers_is_failing_to_neither(passed, total, baseline):
    """No skip field → the charitable branch, where the baseline DOES apply.

    The audit spells it "PASS (baseline)"; the validator returns ok. This is the
    card's motivating case — an onboarded project reporting bare counts.
    """
    assert _audit_says_failing(passed, total, None, baseline) is False
    assert _test_phase_says_failing(passed, total, None, baseline) is False


@pytest.mark.covers("FR-01.06")
def test_a_gap_beyond_the_baseline_is_where_the_two_deliberately_differ():
    """Not a divergence to fix — they are answering different questions.

    With no breakdown and a gap larger than the baseline, the audit renders
    ``PASS (n skipped)``: it is describing *merged historical* work, which was
    green at merge by the Iron Law, so a later gap is read as skips. The
    validator is gating the *current* run, where an unexplained gap may well be
    failures; downgrading it to "assume skips" would be precisely the dishonest
    green this iterate removes.

    Pinned so the difference stays deliberate and nobody "fixes" it into
    agreement in either direction.
    """
    assert _audit_says_failing(8, 10, None, 1) is False       # PASS (2 skipped)
    assert _test_phase_says_failing(8, 10, None, 1) is True   # WARNING
    # The pre-existing validator behaviour, unchanged by this iterate:
    assert _test_phase_says_failing(8, 10, None, 0) is True


@pytest.mark.covers("FR-01.06")
@pytest.mark.parametrize(
    ("passed", "total", "skipped", "baseline"),
    [(8, 10, 0, 2), (8, 10, 0, 1), (9, 10, 0, 1), (90, 100, 8, 5)],
)
def test_they_agree_that_an_exact_residual_is_not_waived_by_the_baseline(
    passed, total, skipped, baseline,
):
    """Explicit skip count → the exact branch, where the baseline does NOT apply.

    This is the case the parity test was written for and immediately caught:
    the validator originally applied the allowance here while the audit did not
    — a two-truths divergence in exactly the projects that carry a baseline
    file. The audit's side is the deliberate one (compliance's
    ``test_explicit_residual_ignores_baseline_charity``: an exactly-counted
    failure must not be waived by a count, or the rendered cell contradicts the
    D4 detective), so the validator moved.
    """
    assert _audit_says_failing(passed, total, skipped, baseline) is True
    assert _test_phase_says_failing(passed, total, skipped, baseline) is True


@pytest.mark.covers("FR-01.06")
def test_an_explicit_failed_count_matches_the_audits_derived_one():
    """The one extra signal the test phase has must not change the answer.

    The validator prefers ``unit.failed`` when the layer reports it; the audit
    derives the same number from ``total - passed - skipped``. Where both are
    available and consistent, the verdict is identical.
    """
    for passed, total, skipped in [(90, 100, 10), (90, 100, 9), (90, 100, 0)]:
        derived = max(0, total - passed - skipped)
        assert genuine_failure_count(
            passed=passed, total=total, failed=derived, skipped=skipped,
        ) == genuine_failure_count(
            passed=passed, total=total, failed=None, skipped=skipped,
        ) == derived


@pytest.mark.covers("FR-01.06")
def test_within_baseline_still_mirrors_the_audits_no_skip_field_branch():
    """With no skip count, the audit reads the whole gap charitably and the
    ``within_baseline`` helper reproduces its baseline arm exactly."""
    assert within_baseline(8, 10, 2) is True
    assert progression_result(8, 10, None, 2) == "PASS (baseline)"
    assert within_baseline(8, 10, 1) is False
    assert progression_result(8, 10, None, 1) == "PASS (2 skipped)"
