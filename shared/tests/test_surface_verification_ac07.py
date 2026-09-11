"""FR-01.11/AC07: `verify_surface`'s zero-tests and happy-path exit codes.

Split out of `test_surface_verification.py` (Naming & Structure — the parent
file was already at its grandfathered bloat-baseline ceiling; moving these
two pre-existing tests here rather than tagging them in place keeps both
files within their own limit without inventing a duplicate harness). Same
imports/fixtures as the parent file; no new test infrastructure.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from surface_verification import (  # noqa: E402  (after sys.path tweak)
    EXIT_OK,
    EXIT_ZERO_TESTS,
    verify_surface,
)


@pytest.mark.covers("FR-01.11/AC07")  # producing only documents counts as no test
def test_zero_tests_exits_2(tmp_path):
    """Greedy-filter trap: runner exits 0 but matched zero tests."""
    code, block = verify_surface(
        project_root=tmp_path,
        run_id="iterate-2026-01-01-foo",
        surface="cli",
        runner=[sys.executable, "-c", "print('no tests collected')"],
        justification=None,
        tests_run_override=None,
    )
    assert code == EXIT_ZERO_TESTS
    assert block["tests_run"] == 0


@pytest.mark.covers("FR-01.11/AC07")  # a real runner process actually executes
def test_happy_path_exit_0(tmp_path):
    code, block = verify_surface(
        project_root=tmp_path,
        run_id="iterate-2026-01-01-foo",
        surface="cli",
        runner=[sys.executable, "-c", "print('=== 3 passed in 0.1s ===')"],
        justification=None,
        tests_run_override=None,
    )
    assert code == EXIT_OK
    assert block["tests_run"] == 3
    assert block["exit_code"] == 0
