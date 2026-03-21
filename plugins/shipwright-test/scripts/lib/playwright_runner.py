"""Playwright E2E test runner — wraps `npx playwright test` and parses results.

Usage:
    uv run playwright_runner.py --cwd /path/to/project [--reporter json]

Reads e2e-results.json (Playwright JSON reporter output) and returns structured results.
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path


def parse_playwright_json(results_path: Path) -> dict:
    """Parse Playwright JSON reporter output (e2e-results.json).

    Returns structured summary with pass/fail/skip counts.
    """
    if not results_path.exists():
        return {
            "parsed": False,
            "error": f"Results file not found: {results_path}",
        }

    try:
        data = json.loads(results_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return {"parsed": False, "error": f"Invalid JSON in results: {e}"}

    # Playwright JSON format has suites → specs → tests → results
    suites = data.get("suites", [])
    total = 0
    passed = 0
    failed = 0
    skipped = 0
    failures: list[dict] = []

    def walk_suites(suite_list: list) -> None:
        nonlocal total, passed, failed, skipped
        for suite in suite_list:
            for spec in suite.get("specs", []):
                for test in spec.get("tests", []):
                    for result in test.get("results", []):
                        total += 1
                        status = result.get("status", "unknown")
                        if status == "passed":
                            passed += 1
                        elif status in ("failed", "timedOut"):
                            failed += 1
                            failures.append({
                                "title": spec.get("title", "unknown"),
                                "file": spec.get("file", ""),
                                "status": status,
                                "error": _extract_error(result),
                            })
                        elif status == "skipped":
                            skipped += 1
            # Recurse into nested suites
            walk_suites(suite.get("suites", []))

    walk_suites(suites)

    return {
        "parsed": True,
        "total": total,
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "failures": failures,
        "duration_ms": data.get("stats", {}).get("duration", 0),
    }


def _extract_error(result: dict) -> str:
    """Extract error message from a Playwright test result."""
    error = result.get("error", {})
    if isinstance(error, dict):
        return error.get("message", "")
    if isinstance(error, str):
        return error
    # Check attachments for error screenshots
    return ""


def run_playwright(cwd: Path, timeout: int = 300) -> dict:
    """Run `npx playwright test` and return structured results."""
    results_path = cwd / "e2e-results.json"

    # Clean old results
    if results_path.exists():
        results_path.unlink()

    try:
        proc = subprocess.run(
            ["npx", "playwright", "test"],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
        )
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "error": f"Playwright tests timed out after {timeout}s",
        }
    except OSError as e:
        return {
            "success": False,
            "error": f"Failed to run playwright: {e}",
        }

    # Parse JSON results
    parsed = parse_playwright_json(results_path)

    if not parsed.get("parsed"):
        # Fallback: use exit code
        return {
            "success": proc.returncode == 0,
            "stdout": proc.stdout[:3000] if proc.stdout else "",
            "stderr": proc.stderr[:3000] if proc.stderr else "",
            "returncode": proc.returncode,
            "parse_error": parsed.get("error", "No results file"),
        }

    return {
        "success": parsed["failed"] == 0,
        **parsed,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Playwright E2E tests")
    parser.add_argument("--cwd", required=True, help="Target project directory")
    parser.add_argument("--timeout", type=int, default=300, help="Timeout in seconds")
    args = parser.parse_args()

    cwd = Path(args.cwd).resolve()
    result = run_playwright(cwd, args.timeout)
    print(json.dumps(result, indent=2))
    return 0 if result.get("success") else 1


if __name__ == "__main__":
    sys.exit(main())
