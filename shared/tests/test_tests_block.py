"""Direct unit tests for the shared skip-vs-fail SSOT (shared/scripts/tests_block.py).

The three consumers (record_event write guard, D4 detective, test-evidence +
dashboard renderers) go through this module so they cannot disagree on the
present/absent predicate (``isinstance(int)``) or the arithmetic. These tests pin
the contract in isolation; the consumer tests exercise the wiring.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_SHARED_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

from tests_block import progression_result, skip_suffix, validate_tests_block  # noqa: E402


class TestValidateTestsBlock:
    def test_valid_block_ok(self):
        validate_tests_block({"passed": 8, "total": 10, "skipped": 2})  # no raise

    def test_absent_skipped_ok(self):
        validate_tests_block({"passed": 10, "total": 10})  # no raise

    def test_passed_plus_skipped_exceeds_total(self):
        with pytest.raises(ValueError, match=r"> total \(10\)"):
            validate_tests_block({"passed": 9, "total": 10, "skipped": 3})

    def test_negative_skipped(self):
        with pytest.raises(ValueError, match="non-negative integer"):
            validate_tests_block({"passed": 8, "total": 10, "skipped": -1})

    def test_non_int_skipped(self):
        with pytest.raises(ValueError, match="non-negative integer"):
            validate_tests_block({"passed": 8, "total": 10, "skipped": "2"})

    def test_bool_skipped(self):
        with pytest.raises(ValueError, match="non-negative integer"):
            validate_tests_block({"passed": 8, "total": 10, "skipped": True})


class TestSkipSuffix:
    @pytest.mark.parametrize("tests,expected", [
        ({"skipped": 3}, " (3 skipped)"),
        ({"skipped": 0}, ""),
        ({}, ""),
        ({"skipped": "3"}, ""),   # non-int → no suffix (charitable)
    ])
    def test_suffix(self, tests, expected):
        # bool is a should-never-happen at read (validate_tests_block rejects it
        # at write); its read behaviour is left unpinned — all three readers just
        # treat it consistently as int, so there is no cross-reader divergence.
        assert skip_suffix(tests) == expected


class TestProgressionResult:
    def test_zero_total(self):
        assert progression_result(0, 0, None, 0) == "—"

    def test_legacy_all_pass(self):
        assert progression_result(10, 10, None, 0) == "PASS"

    def test_legacy_gap_is_skips(self):
        assert progression_result(8, 10, None, 0) == "PASS (2 skipped)"

    def test_legacy_gap_within_baseline(self):
        assert progression_result(9, 10, None, 1) == "PASS (baseline)"

    def test_explicit_green_with_skips(self):
        assert progression_result(8, 10, 2, 0) == "PASS (2 skipped)"

    def test_explicit_disclosure_at_passed_equals_total(self):
        assert progression_result(10, 10, 3, 0) == "PASS (3 skipped)"

    def test_explicit_residual_is_fail(self):
        assert progression_result(6, 10, 2, 0) == "FAIL (2 failed, 2 skipped)"

    def test_explicit_residual_ignores_baseline(self):
        # An explicit residual is exact — baseline charity does not apply.
        assert progression_result(6, 10, 2, 5) == "FAIL (2 failed, 2 skipped)"

    def test_non_int_skipped_is_charitable(self):
        # Same predicate as D4/skip_suffix — no crash, gap-based charity.
        assert progression_result(8, 10, "2", 0) == "PASS (2 skipped)"
