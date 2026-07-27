#!/usr/bin/env python3
"""Shared smoke test utility.

Used by shipwright-test and shipwright-deploy to verify a deployment is alive.

Asking once and giving up is how a fifteen-second start-up gets reported as a
failed release and triggers a rollback nobody needed. So when a deadline is
supplied the check keeps asking until the application answers or the deadline
passes — and the deadline belongs to the **target**, declared as
``smoke_test.max_wait_seconds`` in its deploy profile
(``shared/profiles/deploy/<target>.json``) and resolved by ``deploy_profile``.

No deadline means one attempt, which is exactly the behaviour every existing
caller already has.

Usage:
    uv run smoke_test.py --url <url> [--timeout 10] [--health-path /api/health]
    uv run smoke_test.py --url <url> --profile shared/profiles/deploy/jelastic.json
    uv run smoke_test.py --url <url> --poll-interval 5 --max-wait 60

Output (JSON):
    {
        "success": true/false,
        "url": "https://...",
        "status_code": 200,
        "response_time_ms": 150,
        "attempts": 3,
        "waited_ms": 10400,
        "deadline_seconds": 60 | null,
        "policy_source": {"timeout": "profile:jelastic", ...},
        "health_check": { ... } | null,
        "error": null | "message"
    }
"""

import argparse
import json
import sys
import time
import urllib.error
import urllib.request

import deploy_profile

# The shortest request worth making. Only the FIRST attempt may use it to
# straddle a deadline shorter than itself; every later attempt is capped to the
# time actually remaining, so the total wait never exceeds `max_wait` after that.
MIN_ATTEMPT_SECONDS = 1.0


def _probe(url: str, timeout: float) -> tuple[bool, int | None, float | None, str | None]:
    """One request. Returns (ok, status_code, elapsed_ms, error)."""
    start = time.monotonic()
    try:
        req = urllib.request.Request(url, method="GET")
        req.add_header("User-Agent", "shipwright-smoke-test/0.1")

        # Smoke-test target URL comes from the deploy config (operator-supplied at deploy time).
        # nosemgrep: python.lang.security.audit.dynamic-urllib-use-detected.dynamic-urllib-use-detected
        with urllib.request.urlopen(req, timeout=timeout) as response:
            elapsed = (time.monotonic() - start) * 1000
            return 200 <= response.status < 400, response.status, round(elapsed, 1), None
    except urllib.error.HTTPError as e:
        elapsed = (time.monotonic() - start) * 1000
        return False, e.code, round(elapsed, 1), f"HTTP {e.code}: {e.reason}"
    except urllib.error.URLError as e:
        return False, None, None, f"Connection failed: {e.reason}"
    except TimeoutError:
        return False, None, None, f"Timeout after {timeout}s"
    except Exception as e:  # noqa: BLE001 — a smoke test must never raise at its caller
        return False, None, None, str(e)


def _check_health(url: str, health_path: str, timeout: float) -> dict:
    health_url = f"{url}{health_path}"
    try:
        req = urllib.request.Request(health_url, method="GET")
        req.add_header("User-Agent", "shipwright-smoke-test/0.1")

        # Health URL is the smoke-test URL + a configured health-check path; both from deploy config.
        # nosemgrep: python.lang.security.audit.dynamic-urllib-use-detected.dynamic-urllib-use-detected
        with urllib.request.urlopen(req, timeout=timeout) as response:
            body = response.read().decode("utf-8")
            try:
                return json.loads(body)
            except json.JSONDecodeError:
                return {"raw": body[:500]}
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}


def run_smoke_test(
    url: str,
    timeout: int = deploy_profile.DEFAULT_TIMEOUT,
    health_path: str | None = None,
    *,
    poll_interval: int = deploy_profile.DEFAULT_POLL_INTERVAL,
    max_wait: int | None = None,
    policy_source: dict | None = None,
) -> dict:
    """Ask the deployed application whether it is alive.

    Args:
        url: Base URL to test (e.g., https://app.example.com)
        timeout: Per-request timeout in seconds
        health_path: Optional health endpoint path (e.g., /api/health)
        poll_interval: Seconds between attempts when a deadline is set
        max_wait: Deadline in seconds. ``None`` means a single attempt.
        policy_source: Where each effective value came from (reporting only).

    Returns:
        Result dict with status, timing, attempt evidence, and optional health data.
    """
    if timeout is not None and timeout < 0:
        raise ValueError("timeout must not be negative")
    if max_wait is not None:
        if max_wait < 0:
            raise ValueError("max_wait must not be negative")
        if not poll_interval or poll_interval < 1:
            raise ValueError("poll_interval must be at least 1 second when polling")

    url = url.rstrip("/")
    result = {
        "success": False,
        "url": url,
        "status_code": None,
        "response_time_ms": None,
        "attempts": 0,
        "waited_ms": 0,
        "deadline_seconds": max_wait,
        "policy_source": policy_source or {},
        "health_check": None,
        "error": None,
    }

    started = time.monotonic()
    deadline = None if max_wait is None else started + max_wait

    while True:
        remaining = None if deadline is None else max(0.0, deadline - time.monotonic())
        if remaining is not None and result["attempts"] and remaining <= 0:
            break
        # Never let a request run past the deadline it is meant to respect. Only
        # the very first attempt may exceed it, and only up to MIN_ATTEMPT_SECONDS
        # — a check that never asks at all would be worse than a short overrun.
        if remaining is None:
            attempt_timeout: float = timeout
        elif result["attempts"] == 0:
            attempt_timeout = min(timeout, max(remaining, MIN_ATTEMPT_SECONDS))
        else:
            attempt_timeout = min(timeout, remaining)

        ok, status, elapsed, error = _probe(url, attempt_timeout)
        result["attempts"] += 1
        result["status_code"] = status
        result["response_time_ms"] = elapsed
        result["success"] = ok
        result["error"] = None if ok else error
        result["waited_ms"] = round((time.monotonic() - started) * 1000, 1)

        if ok or deadline is None:
            break
        left = deadline - time.monotonic()
        if left <= 0:
            break
        time.sleep(min(poll_interval, left))

    if not result["success"] and deadline is not None:
        result["error"] = (
            f"{result['error']} (still not answering after {max_wait}s and "
            f"{result['attempts']} attempt(s))"
        )

    if health_path and result["success"]:
        # The health probe counts against the same deadline as the liveness one.
        health_timeout = timeout if deadline is None else min(
            timeout, max(deadline - time.monotonic(), MIN_ATTEMPT_SECONDS))
        result["health_check"] = _check_health(url, health_path, health_timeout)

    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="HTTP smoke test")
    parser.add_argument("--url", required=True, help="URL to test")
    parser.add_argument("--timeout", type=int, help="Per-request timeout in seconds")
    parser.add_argument("--health-path", default=None, help="Health endpoint path")
    parser.add_argument("--poll-interval", type=int, help="Seconds between attempts")
    parser.add_argument("--max-wait", type=int,
                        help="Deadline in seconds; omit for a single attempt")
    parser.add_argument("--profile", help="Deploy profile supplying the target's deadline")
    args = parser.parse_args()

    try:
        profile = deploy_profile.load_profile(args.profile) if args.profile else None
        policy = deploy_profile.smoke_policy(
            profile,
            timeout=args.timeout,
            poll_interval=args.poll_interval,
            max_wait=args.max_wait,
            health_path=args.health_path,
        )
        result = run_smoke_test(
            args.url, policy.timeout, policy.health_path,
            poll_interval=policy.poll_interval,
            max_wait=policy.max_wait,
            policy_source=policy.source,
        )
    except (deploy_profile.ProfileError, ValueError) as exc:
        print(json.dumps({"success": False, "url": args.url, "error": str(exc)}, indent=2))
        return 2

    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
