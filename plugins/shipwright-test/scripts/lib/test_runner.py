#!/usr/bin/env python3
"""Profile-aware test runner.

Determines the correct test command based on stack profile and runs it.
Reads commands dynamically from profile JSON when --profile-path is provided,
falling back to hardcoded defaults otherwise.

Usage:
    uv run test_runner.py --profile <name> --layer <unit|integration|pgtap|e2e|all>
    uv run test_runner.py --profile-path <path/to/profile.json> --layer <layer>
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


# Profile → test commands (fallback when --profile-path not provided)
PROFILE_TEST_COMMANDS = {
    "supabase-nextjs": {
        "unit": "npx vitest run",
        "integration": "npx vitest run --config vitest.integration.config.ts",
        "pgtap": "npx supabase test db",
        "e2e": "npx playwright test",
    },
}

DEFAULT_COMMANDS = {
    "unit": "npm test",
    "integration": "npx vitest run --config vitest.integration.config.ts",
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
        # shell=True is required for cross-platform support of Windows .cmd shims
        # (npm.cmd, yarn.cmd, pnpm.cmd) which subprocess cannot resolve with shell=False.
        # `command` comes from the trusted shipwright profile configuration (testing.commands.*),
        # not from user input. Profile files are project-internal and version-controlled.
        # nosemgrep: python.lang.security.audit.subprocess-shell-true.subprocess-shell-true
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


def get_test_command(profile: str, layer: str, profile_path: Path | None = None) -> str:
    """Get the test command for a profile and layer.

    When profile_path is provided, reads commands dynamically from the profile
    JSON file (single source of truth). Falls back to hardcoded defaults otherwise.
    """
    if profile_path and profile_path.exists():
        try:
            profile_data = json.loads(profile_path.read_text(encoding="utf-8"))
            testing = profile_data.get("testing", {})
            if layer == "integration":
                cmd = testing.get("integration", {}).get("command", "")
                if cmd:
                    return cmd
            elif layer == "pgtap":
                cmd = testing.get("db_tests", {}).get("command", "")
                if cmd:
                    return cmd
            elif layer in testing:
                layer_config = testing[layer]
                if isinstance(layer_config, dict) and "command" in layer_config:
                    return layer_config["command"]
        except (json.JSONDecodeError, OSError):
            pass  # Fall back to hardcoded defaults

    commands = PROFILE_TEST_COMMANDS.get(profile, DEFAULT_COMMANDS)
    return commands.get(layer, DEFAULT_COMMANDS.get(layer, f"echo 'No test command for {layer}'"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Profile-aware test runner")
    parser.add_argument("--profile", default="supabase-nextjs", help="Stack profile name")
    parser.add_argument("--layer", default="unit", choices=["unit", "integration", "pgtap", "e2e", "all"])
    parser.add_argument("--command", help="Custom test command (overrides profile)")
    parser.add_argument("--cwd", help="Working directory for test execution")
    parser.add_argument("--profile-path", help="Path to profile JSON for dynamic command resolution")
    parser.add_argument("--skip-if-missing", action="store_true",
                        help="Skip gracefully if test dir does not exist (integration/pgtap)")
    args = parser.parse_args()

    profile_path = Path(args.profile_path) if args.profile_path else None

    if args.layer == "all":
        layers = ["unit", "integration", "pgtap", "e2e"]
    else:
        layers = [args.layer]

    results = []
    all_success = True

    # Directory existence checks for skip-if-missing
    skip_dirs = {
        "integration": "tests/integration",
        "pgtap": "supabase/tests/database",
    }

    for layer in layers:
        # Skip layers whose directories don't exist (when --skip-if-missing)
        if args.skip_if_missing and layer in skip_dirs and args.cwd:
            layer_dir = Path(args.cwd) / skip_dirs[layer]
            if not layer_dir.exists():
                results.append({
                    "success": True,
                    "layer": layer,
                    "command": "skipped",
                    "exit_code": 0,
                    "passed": 0,
                    "failed": 0,
                    "total": 0,
                    "duration_seconds": 0,
                    "output": f"Skipped: {skip_dirs[layer]}/ directory does not exist",
                    "skipped": True,
                    "skip_reason": f"no {skip_dirs[layer]}/ directory",
                })
                continue

        if layer == "e2e" and not args.command and args.cwd:
            # Use Playwright runner for structured E2E results
            from playwright_runner import run_playwright
            result = run_playwright(Path(args.cwd))
            result["layer"] = "e2e"
        else:
            command = args.command or get_test_command(args.profile, layer, profile_path)
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
