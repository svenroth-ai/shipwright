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


# ---------------------------------------------------------------------------
# Named blockers on a pending verdict (iterate-2026-07-27-name-the-blocker)
# ---------------------------------------------------------------------------
#
# PR #439 sat green for ~25 minutes with auto-merge armed while this watcher
# reported only that it had waited. The cause was one unresolved review thread.
# A pending verdict now carries the named reasons the PR is not merging; the
# terminal verdicts and their exit codes are deliberately untouched.

_PENDING = {
    "state": "OPEN", "mergeStateStatus": "BLOCKED",
    "url": "https://github.com/o/n/pull/439", "baseRefName": "main",
    "statusCheckRollup": [_checkrun("ci", "COMPLETED", "SUCCESS")],
}


def _probe_returning(report):
    seen = {}

    def probe(**kwargs):
        seen.update(kwargs)
        return report

    return probe, seen


def test_pending_timeout_carries_named_blockers():
    report = {"merge_state_status": "BLOCKED", "blocking": True,
              "causes": [{"kind": "unresolved_review_threads", "count": 1}], "unknown": []}
    probe, _ = _probe_returning(report)
    ticks = iter([0.0, 999.0])

    result = wpd.watch(
        "439", fetch=lambda pr, repo: _PENDING, sleep=lambda s: None,
        now=lambda: next(ticks), timeout_seconds=10.0, poll_seconds=0,
        probe_blockers=probe,
    )

    assert result["status"] == "pending" and result["timed_out"] is True
    assert result["blockers"] == report


def test_the_probe_is_told_which_pr_and_branch_to_look_at():
    """owner / name / number come from the `url` the watcher already fetches, so
    naming the blocker costs no extra call to resolve the repo."""
    probe, seen = _probe_returning({"causes": [], "unknown": []})
    ticks = iter([0.0, 999.0])

    wpd.watch(
        "439", fetch=lambda pr, repo: _PENDING, sleep=lambda s: None,
        now=lambda: next(ticks), timeout_seconds=10.0, poll_seconds=0,
        probe_blockers=probe,
    )

    assert seen["owner"] == "o" and seen["name"] == "n" and seen["number"] == 439
    assert seen["branch"] == "main"
    assert seen["merge_state"] == "BLOCKED"


def test_single_poll_mode_also_names_blockers():
    probe, _ = _probe_returning({"causes": [{"kind": "x"}], "unknown": []})
    result = wpd.watch("439", fetch=lambda pr, repo: _PENDING, once=True, probe_blockers=probe)
    assert result["status"] == "pending"
    assert result["blockers"]["causes"] == [{"kind": "x"}]


def test_terminal_verdicts_are_not_probed_and_not_changed():
    """The contract F11 depends on: merged / closed / checks_failed keep their
    exact shape and exit codes. A blocker probe on a merged PR is pointless and
    would be a behaviour change in the one path that already works."""
    called = {"n": 0}

    def probe(**kwargs):
        called["n"] += 1
        return {}

    merged = wpd.watch("1", fetch=lambda pr, repo: {"state": "MERGED", "statusCheckRollup": []},
                       probe_blockers=probe)
    failed = wpd.watch(
        "1", fetch=lambda pr, repo: {"state": "OPEN", "statusCheckRollup": [
            _checkrun("ci", "COMPLETED", "FAILURE")]},
        probe_blockers=probe,
    )

    assert merged == {"status": "merged"}
    assert failed["status"] == "checks_failed" and "blockers" not in failed
    assert called["n"] == 0


def test_a_probe_that_raises_never_costs_the_verdict():
    """A diagnostic must not be able to turn a usable pending verdict into a
    crash — the watcher's job is the verdict; the blocker list is extra."""
    def boom(**kwargs):
        raise RuntimeError("graphql exploded")

    result = wpd.watch("439", fetch=lambda pr, repo: _PENDING, once=True, probe_blockers=boom)

    assert result["status"] == "pending"
    assert result["blockers"]["unknown"][0]["source"] == "probe"


def test_an_unparseable_url_degrades_to_unknown_not_a_crash():
    payload = dict(_PENDING, url="not-a-url")
    result = wpd.watch("439", fetch=lambda pr, repo: payload, once=True)
    assert result["status"] == "pending"
    assert result["blockers"]["unknown"][0]["source"] == "probe"


def test_exit_code_for_pending_is_unchanged():
    assert wpd._exit_code("pending") == 4
    assert wpd._exit_code("merged") == 0
    assert wpd._exit_code("checks_failed") == 2
    assert wpd._exit_code("closed") == 3


def test_pending_report_names_the_cause_in_plain_words():
    """What the operator actually reads. The old line said only that it timed
    out; this one has to say what is holding the PR up."""
    result = {
        "status": "pending", "timed_out": True,
        "blockers": {
            "merge_state_status": "BLOCKED", "blocking": True,
            "causes": [
                {"kind": "unresolved_review_threads", "count": 2},
                {"kind": "required_check_never_reported", "checks": ["PR Review"]},
            ],
            "unknown": [],
        },
    }
    line = wpd._render_pending(result)
    assert "BLOCKED" in line
    assert "unresolved_review_threads: 2" in line
    assert "required_check_never_reported: PR Review" in line


def test_pending_report_says_which_sources_it_could_not_check():
    result = {
        "status": "pending", "timed_out": True,
        "blockers": {"merge_state_status": "", "blocking": False, "causes": [],
                     "unknown": [{"source": "required_checks", "reason": "unreadable"}]},
    }
    line = wpd._render_pending(result)
    assert "could not check required_checks" in line
    assert "no blocker found" not in line   # unknown is NOT clean


def test_pending_report_with_nothing_found_says_so_without_implying_a_fault():
    result = {"status": "pending", "timed_out": False,
              "blockers": {"merge_state_status": "CLEAN", "blocking": False,
                           "causes": [], "unknown": []}}
    line = wpd._render_pending(result)
    assert "no blocker found" in line and "still queued" in line
