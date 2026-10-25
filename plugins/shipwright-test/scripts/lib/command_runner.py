#!/usr/bin/env python3
"""Run one test command and read pass/fail counts out of its output.

Split out of `test_runner.py` (which resolves WHICH command to run) so that file
stays under its size cap. Re-exported there, so `test_runner.run_tests` and
`test_runner.parse_test_output` are unchanged for callers and tests.
"""

import subprocess
import time


def parse_test_output(output: str) -> dict:
    """Try to extract pass/fail counts from test runner output.

    Supports Vitest and pytest output formats.
    """
    import re

    result = {"passed": 0, "failed": 0, "total": 0}

    # Vitest: "Tests  42 passed (42)"
    vitest_match = re.search(r"(\d+)\s+passed.*?(\d+)\s+failed", output)
    if not vitest_match:
        vitest_match = re.search(r"(\d+)\s+passed", output)
        if vitest_match:
            result["passed"] = int(vitest_match.group(1))
            result["total"] = result["passed"]
            return result

    # pytest: "42 passed, 3 failed"
    pytest_match = re.search(r"(\d+)\s+passed", output)
    if pytest_match:
        result["passed"] = int(pytest_match.group(1))

    failed_match = re.search(r"(\d+)\s+failed", output)
    if failed_match:
        result["failed"] = int(failed_match.group(1))

    result["total"] = result["passed"] + result["failed"]
    return result


def run_tests(command: str, cwd: str | None = None) -> dict:
    """Run a test command and return structured results."""
    start = time.monotonic()

    try:
        # shell=True is required for cross-platform support of Windows .cmd shims
        # (npm.cmd, yarn.cmd, pnpm.cmd) which subprocess cannot resolve with shell=False.
        # `command` comes from the trusted shipwright profile configuration (testing.commands.*),
        # not from user input. Profile files are project-internal and version-controlled.
        proc = subprocess.run(
            command,
            shell=True,  # nosemgrep: python.lang.security.audit.subprocess-shell-true.subprocess-shell-true
            capture_output=True,
            text=True,
            encoding="utf-8",
            cwd=cwd,
            timeout=300,  # 5 minute timeout
        )
        elapsed = time.monotonic() - start

        combined_output = proc.stdout + proc.stderr
        counts = parse_test_output(combined_output)

        return {
            "success": proc.returncode == 0,
            "command": command,
            "exit_code": proc.returncode,
            "passed": counts["passed"],
            "failed": counts["failed"],
            "total": counts["total"],
            "duration_seconds": round(elapsed, 2),
            "output": combined_output[-2000:],  # Last 2000 chars
        }

    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "command": command,
            "exit_code": -1,
            "passed": 0,
            "failed": 0,
            "total": 0,
            "duration_seconds": 300,
            "output": "Test execution timed out after 5 minutes",
        }
    except Exception as e:
        return {
            "success": False,
            "command": command,
            "exit_code": -1,
            "passed": 0,
            "failed": 0,
            "total": 0,
            "duration_seconds": 0,
            "output": str(e),
        }
