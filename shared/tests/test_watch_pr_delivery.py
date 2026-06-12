"""`watch_pr_delivery.classify_delivery` — the pure terminal-state classifier behind
the F11 delivery-watch (iterate-2026-06-12-delivery-watch; memory
`feedback_no_shoot_and_forget`). Given a `gh pr view --json
state,mergeStateStatus,statusCheckRollup` payload, decide whether the PR is
delivered (merged), failed (a Required Check is red), closed, or still pending —
so F11 NEVER declares "done" on an armed-but-unmerged red PR. The poll loop +
gh call are the thin untestable shell; this classifier is the tested core.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))

from tools import watch_pr_delivery as wpd  # noqa: E402


def _checkrun(name, status, conclusion, url="http://x"):
    return {"__typename": "CheckRun", "name": name, "status": status,
            "conclusion": conclusion, "detailsUrl": url}


def _statusctx(context, state, url="http://x"):
    return {"__typename": "StatusContext", "context": context, "state": state, "targetUrl": url}


def test_merged_is_delivered():
    pr = {"state": "MERGED", "mergeStateStatus": "UNKNOWN", "statusCheckRollup": []}
    assert wpd.classify_delivery(pr) == {"status": "merged"}


def test_closed_is_not_delivered():
    pr = {"state": "CLOSED", "mergeStateStatus": "UNKNOWN", "statusCheckRollup": []}
    assert wpd.classify_delivery(pr)["status"] == "closed"


def test_failed_checkrun_is_checks_failed_and_listed():
    pr = {"state": "OPEN", "mergeStateStatus": "BLOCKED", "statusCheckRollup": [
        _checkrun("Python (lint + test)", "COMPLETED", "SUCCESS"),
        _checkrun("Shipwright Security Scan", "COMPLETED", "FAILURE", "http://run/42"),
    ]}
    out = wpd.classify_delivery(pr)
    assert out["status"] == "checks_failed"
    names = [f["name"] for f in out["failed"]]
    assert names == ["Shipwright Security Scan"]
    assert out["failed"][0]["url"] == "http://run/42"


def test_failed_statuscontext_counts_as_failing():
    pr = {"state": "OPEN", "mergeStateStatus": "BLOCKED", "statusCheckRollup": [
        _statusctx("ci/legacy", "FAILURE"),
    ]}
    assert wpd.classify_delivery(pr)["status"] == "checks_failed"


def test_action_required_checkrun_is_failing():
    # ACTION_REQUIRED blocks auto-merge → surface it, don't silently wait forever.
    pr = {"state": "OPEN", "mergeStateStatus": "BLOCKED", "statusCheckRollup": [
        _checkrun("PR Review", "COMPLETED", "ACTION_REQUIRED"),
    ]}
    assert wpd.classify_delivery(pr)["status"] == "checks_failed"


def test_open_with_running_checks_is_pending():
    pr = {"state": "OPEN", "mergeStateStatus": "BLOCKED", "statusCheckRollup": [
        _checkrun("Python (lint + test)", "IN_PROGRESS", None),
        _checkrun("Analyze (python)", "COMPLETED", "SUCCESS"),
    ]}
    out = wpd.classify_delivery(pr)
    assert out["status"] == "pending"


def test_skipped_and_neutral_do_not_count_as_failure():
    # A `needs:`-skipped Tier-1/2 PR Review (conclusion SKIPPED/NEUTRAL) is a PASS,
    # not a failure (B4.5: GitHub treats a skipped required job as success).
    pr = {"state": "OPEN", "mergeStateStatus": "CLEAN", "statusCheckRollup": [
        _checkrun("PR Review", "COMPLETED", "SKIPPED"),
        _checkrun("Decide if review is needed", "COMPLETED", "NEUTRAL"),
        _checkrun("Python (lint + test)", "COMPLETED", "SUCCESS"),
    ]}
    assert wpd.classify_delivery(pr)["status"] == "pending"


def test_missing_rollup_key_is_pending_not_crash():
    # Defensive: a payload without statusCheckRollup must not KeyError.
    assert wpd.classify_delivery({"state": "OPEN"})["status"] == "pending"


def test_watch_loop_polls_pending_until_terminal():
    # The poll loop keeps fetching while pending and returns the first terminal
    # verdict (injected fetch/sleep — no gh, no real time).
    seq = [
        {"state": "OPEN", "statusCheckRollup": [_checkrun("ci", "IN_PROGRESS", None)]},
        {"state": "OPEN", "statusCheckRollup": [_checkrun("ci", "COMPLETED", "SUCCESS")]},
        {"state": "MERGED", "statusCheckRollup": []},
    ]
    calls = {"n": 0}

    def fetch(pr, repo):
        i = min(calls["n"], len(seq) - 1)
        calls["n"] += 1
        return seq[i]

    result = wpd.watch("1", fetch=fetch, sleep=lambda s: None, poll_seconds=0)
    assert result == {"status": "merged"}
    assert calls["n"] == 3  # polled through both pending payloads


def test_watch_loop_times_out_pending_fails_closed():
    # If it never leaves pending, watch() returns pending + timed_out (caller STOPs).
    always_pending = {"state": "OPEN", "statusCheckRollup": [_checkrun("ci", "QUEUED", None)]}
    ticks = iter([0.0, 0.0, 999.0])  # now() crosses the deadline on the 2nd check

    result = wpd.watch(
        "1", fetch=lambda pr, repo: always_pending,
        sleep=lambda s: None, now=lambda: next(ticks),
        timeout_seconds=10.0, poll_seconds=0,
    )
    assert result["status"] == "pending" and result["timed_out"] is True
