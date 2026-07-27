"""Playwright E2E test runner — wraps `npx playwright test` and parses results.

Usage:
    uv run playwright_runner.py --cwd /path/to/project [--reporter json]

Reads e2e-results.json (Playwright JSON reporter output) and returns structured results.

**Counting is per test, not per attempt** (FR-01.06,
iterate-2026-07-27-test-phase-record-honesty). This reader used to walk
``test["results"]`` and count every retry attempt as its own test, so a test
that failed and then passed on retry inflated ``total`` and simultaneously
landed in ``failed`` — the record was wrong in both directions, and the run went
red over a test that passed.

Now each test contributes exactly one outcome, and a test that only passed on
retry is reported as such:

* ``passed + failed + skipped == total``
* ``flaky <= passed`` — flaky is a **subset** of passed, not a fourth bucket.
  It stays a pass and does not block; it is counted separately so a test that
  has needed a retry for weeks becomes visible before it fails for good.
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

# Playwright's per-test verdict, when the reporter emits one.
_TEST_VERDICTS = {"expected", "flaky", "unexpected", "skipped"}
_FAILING_RESULT_STATUSES = {"failed", "timedOut", "interrupted"}


def classify_test(test: dict) -> tuple[str, int]:
    """Return ``(outcome, retries)`` for one Playwright test object.

    ``outcome`` is one of ``passed`` / ``flaky`` / ``failed`` / ``skipped``;
    ``flaky`` means *passed, but not on the first attempt*.

    Playwright's own per-test ``status`` wins whenever it is present. Older
    reporter output (and our fixtures) omit it, so the attempts are read
    instead. The decision table:

    ==========================================  =========  ==================
    Signal                                      Outcome    Retries
    ==========================================  =========  ==================
    ``status == "expected"``                    passed     ``max(retry)``
    ``status == "flaky"``                       flaky      ``max(retry)``
    ``status == "unexpected"``                  failed     ``max(retry)``
    ``status == "skipped"``                     skipped    0
    absent, last attempt passed, >1 attempt     flaky      ``len - 1``
    absent, last attempt passed, 1 attempt      passed     0
    absent, last attempt failed/timedOut/…      failed     ``len - 1``
    absent, every attempt skipped               skipped    0
    no attempts at all, or an unknown status    **failed** 0
    ==========================================  =========  ==================

    The last row is the point: an incomplete or unrecognised record is never
    silently promoted into a pass.
    """
    results = test.get("results")
    if not isinstance(results, list):
        results = []
    results = [r for r in results if isinstance(r, dict)]

    retries = 0
    for r in results:
        retry = r.get("retry")
        if isinstance(retry, int) and not isinstance(retry, bool) and retry > retries:
            retries = retry
    if retries == 0 and len(results) > 1:
        # No explicit `retry` index — attempt count is the next-best signal.
        retries = len(results) - 1

    verdict = test.get("status")
    if verdict in _TEST_VERDICTS:
        if verdict == "expected":
            return "passed", retries
        if verdict == "flaky":
            return "flaky", retries
        if verdict == "unexpected":
            return "failed", retries
        return "skipped", 0

    if not results:
        return "failed", 0

    last = results[-1].get("status")
    if last == "passed":
        # More than one attempt IS the retry signal: Playwright only records a
        # second result after the first did not succeed. Keyed on the attempt
        # count rather than on the earlier statuses so the legacy path matches
        # the table above exactly — an earlier attempt whose status the older
        # reporter spelled differently must not silently lose the retry
        # (external code review on the delivered head).
        return ("flaky" if len(results) > 1 else "passed"), retries
    if last in _FAILING_RESULT_STATUSES:
        return "failed", retries
    if last == "skipped":
        # Only genuinely skipped when nothing else happened — a skip after a
        # failure must not erase the failure from the record.
        if all(r.get("status") == "skipped" for r in results):
            return "skipped", 0
        return "failed", retries

    return "failed", retries


def parse_playwright_json(results_path: Path) -> dict:
    """Parse Playwright JSON reporter output (e2e-results.json).

    Returns a structured summary with per-test pass/fail/skip counts, the
    separate ``flaky`` count, and the flaky tests named with their retry count.
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
    flaky = 0
    failures: list[dict] = []
    flaky_tests: list[dict] = []

    def walk_suites(suite_list: list) -> None:
        nonlocal total, passed, failed, skipped, flaky
        for suite in suite_list:
            for spec in suite.get("specs", []):
                for test in spec.get("tests", []):
                    total += 1
                    outcome, retries = classify_test(test)
                    title = spec.get("title", "unknown")
                    file = spec.get("file", "")

                    if outcome == "skipped":
                        skipped += 1
                    elif outcome == "failed":
                        failed += 1
                        failures.append({
                            "title": title,
                            "file": file,
                            "status": "failed",
                            "error": _last_error(test),
                            "retries": retries,
                        })
                    else:
                        # passed / flaky — flaky is a pass that needed a retry
                        passed += 1
                        if outcome == "flaky":
                            flaky += 1
                            flaky_tests.append({
                                "title": title, "file": file, "retries": retries,
                            })
            # Recurse into nested suites
            walk_suites(suite.get("suites", []))

    walk_suites(suites)

    return {
        "parsed": True,
        "total": total,
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "flaky": flaky,
        "failures": failures,
        "flaky_tests": flaky_tests,
        "duration_ms": data.get("stats", {}).get("duration", 0),
    }


def _last_error(test: dict) -> str:
    """The error from the LAST attempt — what the test finally failed on."""
    results = test.get("results")
    if not isinstance(results, list):
        return ""
    for result in reversed([r for r in results if isinstance(r, dict)]):
        message = _extract_error(result)
        if message:
            return message
    return ""


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
