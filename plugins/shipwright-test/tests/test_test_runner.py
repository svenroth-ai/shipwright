"""Tests for test_runner module."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from lib.test_runner import get_test_command, parse_test_output, run_tests


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


def test_run_tests_failing():
    """Run a command that fails."""
    result = run_tests("exit 1")
    assert result["success"] is False
    assert result["exit_code"] == 1
