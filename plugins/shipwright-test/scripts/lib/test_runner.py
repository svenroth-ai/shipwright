#!/usr/bin/env python3
"""Profile-aware test runner.

Determines the correct test command based on stack profile and runs it.
Order: --command, then the profile JSON (--profile-path, else resolved by NAME
from --profile / the run config: project > user > bundled), then defaults that
apply only to a bundled profile or `generic`/`detecting`. Unknown, corrupt or too
new profile = ERROR (exit 2/3), never a fallback. An undeclared non-unit layer is skipped.

Usage:
    uv run test_runner.py --profile <name> --layer <unit|integration|pgtap|e2e|all>
    uv run test_runner.py --profile-path <path/to/profile.json> --layer <layer>
    uv run test_runner.py --command <custom_command>

Output (JSON): {"success", "layer", "command", "passed", "failed", "total",
"duration_seconds", "output", "profile_source"}; an unusable profile prints
{"success": false, "error", "kind"} and exits 2 or 3.
"""

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

_SHARED = str(Path(__file__).resolve().parents[4] / "shared" / "scripts")
_ADDED = _SHARED not in sys.path
if _ADDED:
    sys.path.append(_SHARED)
import profile_consumer as pc  # noqa: E402

if _ADDED:  # shared/scripts holds a `tools` package that would shadow this plugin's own
    sys.path.remove(_SHARED)


PROFILE_KEYS_READ = ("testing",)  # D6: profile keys this loader consumes (checked against the schema)
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


def resolve_profile_name(cli_profile: str | None, cwd: str | None) -> str:
    """--profile, else the run config's, else legacy `supabase-nextjs` (config names NOTHING).

    A corrupt run config, or a `profile` that is not a string, raises.
    """
    return cli_profile or pc.config_profile(cwd or ".") or "supabase-nextjs"


def load_resolved(profile: str, profile_path, cwd: str | None, *, origin: str = pc.RUN_CONFIG,
                  quiet: bool = False):
    """The ResolvedProfile (provenance on stderr unless quiet); errors are ValueErrors."""
    if profile_path:
        return pc.load_explicit(profile_path, cwd or ".", quiet=quiet)
    return pc.resolve_named(profile, cwd or ".", origin=origin, quiet=quiet)


def uses_legacy_commands(res) -> bool:
    """D9: the name-keyed command table applies to a BUNDLED profile only, by provenance."""
    return res.source == "bundled" and res.name in PROFILE_TEST_COMMANDS


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


def _fail(exc: ValueError) -> int:
    sys.stderr.write(f"error: {exc}\n")
    print(json.dumps({"success": False, **pc.error_fields(exc)}, indent=2))
    return pc.exit_code(exc)


def profile_declares_no_layer(res, layer: str) -> bool:
    """True when a resolved, non-legacy profile FILE has no entry for a non-unit layer (D9).

    The hardcoded `npx` fallbacks only make sense for a node stack; sentinels keep the defaults."""
    if res is None or res.source == "builtin" or layer == "unit" or uses_legacy_commands(res):
        return False
    testing = res.data.get("testing")  # a declared layer without a command is an error later (custom, D9)
    return not (isinstance(testing, dict) and _PROFILE_LAYER_KEYS.get(layer, layer) in testing)


def get_test_command(profile: str, layer: str, profile_path: Path | None = None, *,
                     cwd: str | None = None, resolved=None) -> str:
    """Get the test command for a profile and layer.

    The profile JSON (single source of truth) wins; it is resolved by NAME
    (project > user > bundled) unless `profile_path` / `resolved` is given. Hardcoded
    defaults apply only when the profile declares no command for the layer, and the
    name-keyed table only to a bundled profile (D9). Unknown / invalid raises.
    """
    res = resolved or load_resolved(profile, profile_path, cwd, quiet=True)
    cmd = _profile_layer_command(res.data, layer)
    if cmd:
        return cmd
    if res.source not in ("bundled", "builtin"):  # D9: the default tables are never a custom profile's
        raise pc.ProfileInvalid(f"Profile {res.name!r} ({res.path}) defines no {layer} command; "
                                "add `testing.unit` (or the layer's entry) to it.")
    commands = PROFILE_TEST_COMMANDS[res.name] if uses_legacy_commands(res) else DEFAULT_COMMANDS
    return commands.get(layer, DEFAULT_COMMANDS.get(layer, f"echo 'No test command for {layer}'"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Profile-aware test runner")
    parser.add_argument("--profile", default=None,
                        help="Stack profile name (default: the project's run-config profile)")
    parser.add_argument("--layer", default="unit", choices=["unit", "integration", "pgtap", "e2e", "all"])
    parser.add_argument("--command", help="Custom test command (overrides profile)")
    parser.add_argument("--cwd", help="Working directory for test execution")
    parser.add_argument("--project-root", help="Project root for profile lookup (default: --cwd)")
    parser.add_argument("--profile-path", help="Path to profile JSON for dynamic command resolution")
    parser.add_argument("--skip-if-missing", action="store_true",
                        help="Skip gracefully if test dir does not exist (integration/pgtap)")
    args = parser.parse_args()

    res = profile = None
    if not args.command:  # an explicit --command needs no profile
        try:
            root = args.project_root or args.cwd
            name, path, from_path = pc.name_over_bundled_path(args.profile, args.profile_path)
            profile = name or ("" if path else resolve_profile_name(None, root))
            res = load_resolved(profile, path, root, origin=(
                ("--profile-path" if from_path else "--profile") if name else pc.RUN_CONFIG))
        except ValueError as exc:  # unknown / corrupt / too new: fail loud, name the file, no fallback
            return _fail(exc)
        profile = res.name

    layers = ["unit", "integration", "pgtap", "e2e"] if args.layer == "all" else [args.layer]

    results, all_success = [], True

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

        if not args.command and profile_declares_no_layer(res, layer):
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

        if layer == "e2e" and not args.command and args.cwd and res.source in ("bundled", "builtin"):
            # Use Playwright runner for structured E2E results
            from playwright_runner import run_playwright
            result = run_playwright(Path(args.cwd))
            result["layer"] = "e2e"
        else:
            try:
                command = args.command or get_test_command(profile, layer, resolved=res)
            except ValueError as exc:
                return _fail(exc)
            result = run_tests(command, args.cwd)
            result["layer"] = layer
        results.append(result)
        if not result["success"]:
            all_success = False

    for r in results:
        r["profile_source"] = res.source if res else None
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
