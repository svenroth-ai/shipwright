#!/usr/bin/env python3
"""Profile-aware test runner.

Determines the correct test command based on stack profile and runs it.
Order: --command, then the profile JSON (--profile-path, else located from
--profile / the run config's `profile`), then hardcoded defaults. A non-unit
layer a non-legacy profile does not declare is skipped, not run via a default.

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


# Layer name -> the key the profile's `testing` block files it under.
_PROFILE_LAYER_KEYS = {"unit": "unit", "integration": "integration",
                       "pgtap": "db_tests", "e2e": "e2e"}


def default_profile_path(profile: str | None) -> Path | None:
    """Locate shared/profiles/<profile>.json relative to this file.

    Monorepo (<root>/plugins/shipwright-test/scripts/lib) and the installed
    plugin cache (<marketplace>/shipwright-test/<ver>/scripts/lib) both keep
    `shared/` beside the plugin directories, i.e. under parents[4].
    """
    if not profile:
        return None
    candidate = Path(__file__).resolve().parents[4] / "shared" / "profiles" / f"{profile}.json"
    return candidate if candidate.exists() else None


def resolve_profile_name(cli_profile: str | None, cwd: str | None) -> str:
    """The active profile: --profile, else the project's run config, else legacy default."""
    if cli_profile:
        return cli_profile
    run_config = Path(cwd or ".") / "shipwright_run_config.json"
    try:
        name = json.loads(run_config.read_text(encoding="utf-8")).get("profile")
        if isinstance(name, str) and name:
            return name
    except (json.JSONDecodeError, OSError, AttributeError):
        pass
    return "supabase-nextjs"


def _load_profile(profile_path: Path | None) -> dict | None:
    if profile_path and profile_path.exists():
        try:
            data = json.loads(profile_path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else None
        except (json.JSONDecodeError, OSError):
            return None
    return None


def _profile_layer_command(profile_data: dict, layer: str) -> str:
    """The profile's own command for a layer, or "" when it declares none."""
    testing = profile_data.get("testing")
    if not isinstance(testing, dict):
        return ""
    entry = testing.get(_PROFILE_LAYER_KEYS.get(layer, layer))
    if isinstance(entry, dict) and entry.get("command"):
        return entry["command"]
    if layer == "unit" and isinstance(testing.get("command"), str) and testing["command"]:
        return testing["command"]  # profile-wide runner, e.g. "uv run pytest"
    if isinstance(entry, str) and entry:
        return entry  # flat form, e.g. "unit": "pytest"
    return ""


def profile_declares_no_layer(profile_data: dict | None, profile: str, layer: str) -> bool:
    """True when a loaded, non-legacy profile has no entry at all for a non-unit layer.

    The hardcoded `npx vitest` / `npx playwright` fallbacks only make sense for a
    node stack; running them for e.g. a Python profile is a wrong command, not a
    default. Unit always falls back (a project must have some unit command).
    """
    if profile_data is None or layer == "unit" or profile in PROFILE_TEST_COMMANDS:
        return False
    testing = profile_data.get("testing")
    key = _PROFILE_LAYER_KEYS.get(layer, layer)
    return not (isinstance(testing, dict) and key in testing)


def get_test_command(profile: str, layer: str, profile_path: Path | None = None) -> str:
    """Get the test command for a profile and layer.

    The profile JSON (single source of truth) wins; when `profile_path` is not
    given it is located from `profile` via shared/profiles. Hardcoded defaults
    apply only when the profile declares no command for the layer.
    """
    profile_data = _load_profile(profile_path or default_profile_path(profile))
    if profile_data is not None:
        cmd = _profile_layer_command(profile_data, layer)
        if cmd:
            return cmd

    commands = PROFILE_TEST_COMMANDS.get(profile, DEFAULT_COMMANDS)
    return commands.get(layer, DEFAULT_COMMANDS.get(layer, f"echo 'No test command for {layer}'"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Profile-aware test runner")
    parser.add_argument("--profile", default=None,
                        help="Stack profile name (default: the project's run-config profile)")
    parser.add_argument("--layer", default="unit", choices=["unit", "integration", "pgtap", "e2e", "all"])
    parser.add_argument("--command", help="Custom test command (overrides profile)")
    parser.add_argument("--cwd", help="Working directory for test execution")
    parser.add_argument("--profile-path", help="Path to profile JSON for dynamic command resolution")
    parser.add_argument("--skip-if-missing", action="store_true",
                        help="Skip gracefully if test dir does not exist (integration/pgtap)")
    args = parser.parse_args()

    profile = resolve_profile_name(args.profile, args.cwd)
    profile_path = Path(args.profile_path) if args.profile_path else default_profile_path(profile)
    profile_data = _load_profile(profile_path)

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

        if not args.command and profile_declares_no_layer(profile_data, profile, layer):
            results.append({
                "success": True,
                "layer": layer,
                "command": "skipped",
                "exit_code": 0,
                "passed": 0,
                "failed": 0,
                "total": 0,
                "duration_seconds": 0,
                "output": f"Skipped: profile '{profile}' defines no {layer} tests",
                "skipped": True,
                "skip_reason": f"profile '{profile}' defines no {layer} layer",
            })
            continue

        if layer == "e2e" and not args.command and args.cwd:
            # Use Playwright runner for structured E2E results
            from playwright_runner import run_playwright
            result = run_playwright(Path(args.cwd))
            result["layer"] = "e2e"
        else:
            command = args.command or get_test_command(profile, layer, profile_path)
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
