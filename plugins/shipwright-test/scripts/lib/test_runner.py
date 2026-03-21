#!/usr/bin/env python3
"""Profile-aware test runner.

Determines the correct test command based on stack profile and runs it.

Usage:
    uv run test_runner.py --profile <name> --layer <unit|e2e|all>
    uv run test_runner.py --command <custom_command>

Output (JSON):
    {
        "success": true/false,
        "layer": "unit",
        "command": "npx vitest run",
        "passed": 42,
        "failed": 0,
        "total": 42,
        "duration_seconds": 3.5,
        "output": "..."
    }
"""

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path


# Profile → test commands
PROFILE_TEST_COMMANDS = {
    "supabase-nextjs": {
        "unit": "npx vitest run",
        "e2e": "npx playwright test",
    },
}

DEFAULT_COMMANDS = {
    "unit": "npm test",
    "e2e": "npx playwright test",
}


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
        proc = subprocess.run(
            command,
            shell=True,
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


def get_test_command(profile: str, layer: str) -> str:
    """Get the test command for a profile and layer."""
    commands = PROFILE_TEST_COMMANDS.get(profile, DEFAULT_COMMANDS)
    return commands.get(layer, DEFAULT_COMMANDS.get(layer, f"echo 'No test command for {layer}'"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Profile-aware test runner")
    parser.add_argument("--profile", default="supabase-nextjs", help="Stack profile name")
    parser.add_argument("--layer", default="unit", choices=["unit", "e2e", "all"])
    parser.add_argument("--command", help="Custom test command (overrides profile)")
    parser.add_argument("--cwd", help="Working directory for test execution")
    args = parser.parse_args()

    if args.layer == "all":
        layers = ["unit", "e2e"]
    else:
        layers = [args.layer]

    results = []
    all_success = True

    for layer in layers:
        command = args.command or get_test_command(args.profile, layer)
        result = run_tests(command, args.cwd)
        result["layer"] = layer
        results.append(result)
        if not result["success"]:
            all_success = False

    if len(results) == 1:
        print(json.dumps(results[0], indent=2))
    else:
        print(json.dumps({
            "success": all_success,
            "layers": results,
        }, indent=2))

    return 0 if all_success else 1


if __name__ == "__main__":
    sys.exit(main())
