#!/usr/bin/env python3
"""Shared smoke test utility.

Used by shipwright-test and shipwright-deploy to verify a deployment is alive.

Usage:
    uv run smoke_test.py --url <url> [--timeout 10] [--health-path /api/health]

Output (JSON):
    {
        "success": true/false,
        "url": "https://...",
        "status_code": 200,
        "response_time_ms": 150,
        "health_check": { ... } | null,
        "error": null | "message"
    }
"""

import argparse
import json
import sys
import time
import urllib.request
import urllib.error


def run_smoke_test(
    url: str,
    timeout: int = 10,
    health_path: str | None = None,
) -> dict:
    """Run HTTP smoke test against a URL.

    Args:
        url: Base URL to test (e.g., https://app.example.com)
        timeout: Request timeout in seconds
        health_path: Optional health endpoint path (e.g., /api/health)

    Returns:
        Result dict with status, timing, and optional health data.
    """
    # Normalize URL
    url = url.rstrip("/")

    result = {
        "success": False,
        "url": url,
        "status_code": None,
        "response_time_ms": None,
        "health_check": None,
        "error": None,
    }

    # Test main URL
    try:
        start = time.monotonic()
        req = urllib.request.Request(url, method="GET")
        req.add_header("User-Agent", "shipwright-smoke-test/0.1")

        # Smoke-test target URL comes from the deploy config (operator-supplied at deploy time).
        # nosemgrep: python.lang.security.audit.dynamic-urllib-use-detected.dynamic-urllib-use-detected
        with urllib.request.urlopen(req, timeout=timeout) as response:
            elapsed = (time.monotonic() - start) * 1000
            result["status_code"] = response.status
            result["response_time_ms"] = round(elapsed, 1)
            result["success"] = 200 <= response.status < 400

    except urllib.error.HTTPError as e:
        elapsed = (time.monotonic() - start) * 1000
        result["status_code"] = e.code
        result["response_time_ms"] = round(elapsed, 1)
        result["error"] = f"HTTP {e.code}: {e.reason}"

    except urllib.error.URLError as e:
        result["error"] = f"Connection failed: {e.reason}"

    except TimeoutError:
        result["error"] = f"Timeout after {timeout}s"

    except Exception as e:
        result["error"] = str(e)

    # Health check (optional)
    if health_path and result["success"]:
        health_url = f"{url}{health_path}"
        try:
            req = urllib.request.Request(health_url, method="GET")
            req.add_header("User-Agent", "shipwright-smoke-test/0.1")

            # Health URL is the smoke-test URL + a configured health-check path; both from deploy config.
            # nosemgrep: python.lang.security.audit.dynamic-urllib-use-detected.dynamic-urllib-use-detected
            with urllib.request.urlopen(req, timeout=timeout) as response:
                body = response.read().decode("utf-8")
                try:
                    result["health_check"] = json.loads(body)
                except json.JSONDecodeError:
                    result["health_check"] = {"raw": body[:500]}

        except Exception as e:
            result["health_check"] = {"error": str(e)}

    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="HTTP smoke test")
    parser.add_argument("--url", required=True, help="URL to test")
    parser.add_argument("--timeout", type=int, default=10, help="Timeout in seconds")
    parser.add_argument("--health-path", default=None, help="Health endpoint path")
    args = parser.parse_args()

    result = run_smoke_test(args.url, args.timeout, args.health_path)
    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
