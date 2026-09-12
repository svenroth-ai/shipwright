"""Tests for test_runner module."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from lib.test_runner import get_test_command, parse_test_output, run_tests

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "lib" / "test_runner.py"


def test_get_command_supabase_nextjs_unit():
    cmd = get_test_command("supabase-nextjs", "unit")
    assert "vitest" in cmd


def test_get_command_supabase_nextjs_e2e():
    cmd = get_test_command("supabase-nextjs", "e2e")
    assert "playwright" in cmd


def test_get_command_unknown_profile():
    cmd = get_test_command("unknown-profile", "unit")
    assert "npm test" in cmd


def test_parse_vitest_output():
    output = "Tests  42 passed (42)\nDuration  3.5s"
    result = parse_test_output(output)
    assert result["passed"] == 42
    assert result["total"] == 42


def test_parse_pytest_output():
    output = "===== 15 passed, 2 failed in 1.23s ====="
    result = parse_test_output(output)
    assert result["passed"] == 15
    assert result["failed"] == 2
    assert result["total"] == 17


def test_run_tests_echo():
    """Run a simple echo command as test."""
    result = run_tests("echo 'all good'")
    assert result["success"] is True
    assert result["exit_code"] == 0


@pytest.mark.covers("FR-01.06/AC01")
def test_run_tests_failing():
    """AC1 — a real command is actually run and its real outcome is reported,
    not a summary of what was expected: a failing command must be reported as
    failed even though the caller never told the runner to expect a failure."""
    result = run_tests("exit 1")
    assert result["success"] is False
    assert result["exit_code"] == 1


@pytest.mark.covers("FR-01.06/AC04")
def test_skip_if_missing_records_not_run_with_a_reason_never_a_pass(tmp_path):
    """AC4 — a level that could not reach what it needs (no
    tests/integration/ directory here) is recorded as not-run, with the
    reason, and never as passed."""
    proc = subprocess.run(
        [sys.executable, str(_SCRIPT), "--layer", "integration",
         "--cwd", str(tmp_path), "--skip-if-missing"],
        capture_output=True, text=True, encoding="utf-8", timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    result = json.loads(proc.stdout)
    assert result["skipped"] is True
    assert result["skip_reason"] == "no tests/integration/ directory"
    # Never silently promoted into "passed": zero tests were counted, and the
    # record itself carries a reason rather than a bare pass.
    assert result["passed"] == 0
    assert result["total"] == 0
