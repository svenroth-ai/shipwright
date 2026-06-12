#!/usr/bin/env python3
"""Watch a PR to DELIVERY — the F11 anti-"shoot-and-forget" gate
(iterate-2026-06-12-delivery-watch; memory `feedback_no_shoot_and_forget`).

"Delivered" = the PR is actually MERGED with all Required Checks GREEN. Arming
auto-merge is NOT delivery: a check can fail afterward and the PR sits BLOCKED.
This polls ``gh pr view --json state,mergeStateStatus,statusCheckRollup`` until a
terminal state and reports it, so F11 never declares "done" on an armed-but-red PR.

Pure core: :func:`classify_delivery` (testable, no gh) maps a payload to one of
``merged`` / ``checks_failed`` / ``closed`` / ``pending``. :func:`watch` is the thin
gh+sleep shell. Host-specific (gh) by nature — PR delivery IS a GitHub fact; the
iterate's host-agnostic *correctness* guarantees are unaffected.

Exit codes: 0 merged · 2 checks_failed · 3 closed · 4 pending-timeout · 5 gh-error.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time

#: CheckRun conclusions that mean "this required check will not go green on its own".
_FAILING_CONCLUSIONS = frozenset(
    {"FAILURE", "CANCELLED", "TIMED_OUT", "STARTUP_FAILURE", "ACTION_REQUIRED"}
)
#: Legacy StatusContext states that mean failure.
_FAILING_STATES = frozenset({"FAILURE", "ERROR"})

_GH_FIELDS = "state,mergeStateStatus,statusCheckRollup,url"


def _failing_checks(rollup: list[dict]) -> list[dict]:
    """The subset of ``statusCheckRollup`` entries that are red (CheckRun conclusion
    or StatusContext state). SKIPPED / NEUTRAL / SUCCESS / running are NOT failures —
    a ``needs:``-skipped required job is a pass (B4.5)."""
    failed: list[dict] = []
    for c in rollup or []:
        if c.get("__typename") == "StatusContext":
            if (c.get("state") or "").upper() in _FAILING_STATES:
                failed.append({"name": c.get("context", "?"), "url": c.get("targetUrl", "")})
        else:  # CheckRun (or unknown typename — treat as a check)
            if (c.get("conclusion") or "").upper() in _FAILING_CONCLUSIONS:
                failed.append({"name": c.get("name", "?"), "url": c.get("detailsUrl", "")})
    return failed


def classify_delivery(pr: dict) -> dict:
    """Map a ``gh pr view`` payload to a terminal-or-pending verdict.

    Returns ``{"status": "merged"|"closed"|"checks_failed"|"pending", ...}``.
    ``checks_failed`` carries ``failed`` (a list of ``{name, url}``). A PR that is
    OPEN with no red checks is ``pending`` (still running, or merge blocked for a
    non-check reason like behind/required-review) — keep watching, never "done"."""
    state = (pr.get("state") or "").upper()
    if state == "MERGED":
        return {"status": "merged"}
    if state == "CLOSED":
        return {"status": "closed"}
    failed = _failing_checks(pr.get("statusCheckRollup") or [])
    if failed:
        return {"status": "checks_failed", "failed": failed}
    return {"status": "pending"}


def _gh_pr_json(pr: str, repo: str | None) -> dict:
    """Fetch the PR payload via gh. Raises RuntimeError on a gh failure."""
    cmd = ["gh", "pr", "view", pr, "--json", _GH_FIELDS]
    if repo:
        cmd += ["--repo", repo]
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or "gh pr view failed").strip()[:300])
    return json.loads(proc.stdout)


def watch(
    pr: str,
    *,
    repo: str | None = None,
    timeout_seconds: float = 1800.0,
    poll_seconds: float = 30.0,
    once: bool = False,
    fetch=_gh_pr_json,
    sleep=time.sleep,
    now=time.monotonic,
) -> dict:
    """Poll until a terminal verdict (merged/closed/checks_failed) or timeout.
    Returns the classify_delivery result, augmented with ``{"timed_out": True}`` on
    a pending timeout. ``fetch``/``sleep``/``now`` are injectable for tests."""
    deadline = now() + timeout_seconds
    while True:
        verdict = classify_delivery(fetch(pr, repo))
        if verdict["status"] != "pending" or once:
            return verdict
        if now() >= deadline:
            verdict["timed_out"] = True
            return verdict
        sleep(poll_seconds)


def _exit_code(status: str) -> int:
    return {"merged": 0, "checks_failed": 2, "closed": 3, "pending": 4}.get(status, 4)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Watch a PR to delivery (merged + green)")
    p.add_argument("--pr", required=True, help="PR number or URL")
    p.add_argument("--repo", default=None, help="owner/name (default: cwd's repo)")
    p.add_argument("--timeout-seconds", type=float, default=1800.0)
    p.add_argument("--poll-seconds", type=float, default=30.0)
    p.add_argument("--once", action="store_true", help="single poll, no loop")
    args = p.parse_args(argv)

    try:
        result = watch(
            args.pr, repo=args.repo,
            timeout_seconds=args.timeout_seconds, poll_seconds=args.poll_seconds,
            once=args.once,
        )
    except RuntimeError as exc:
        print(json.dumps({"status": "gh_error", "error": str(exc)}, indent=2))
        return 5
    print(json.dumps(result, indent=2))
    if result["status"] == "checks_failed":
        print(
            "NOT DELIVERED — Required Check(s) failed: "
            + ", ".join(f"{f['name']} ({f['url']})" for f in result["failed"]),
            file=sys.stderr,
        )
    return _exit_code(result["status"])


if __name__ == "__main__":
    raise SystemExit(main())
