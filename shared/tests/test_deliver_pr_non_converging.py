"""The PR-review gate repeating itself, end to end (trg-ac24ec5b, PR #690).

Split out of ``test_deliver_pr.py`` to keep both files under the 300-line
source limit, the same reason ``test_deliver_pr_self_merge.py`` and
``test_deliver_pr_summary.py`` exist as their own files. Its own subject: the
full ladder, host faked, escalating a `checks_failed` verdict to
`non_converging`/exit 8 exactly when the last two `PR Review` BLOCK comments
recur — and never otherwise.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))
sys.path.append(str(Path(__file__).resolve().parent))

from tools.deliver_pr import EXIT_CHECKS_FAILED, EXIT_NON_CONVERGING, deliver  # noqa: E402

from _pr_delivery_fakes import BASE, HEAD, REPO, _Host, _Proc, _watcher  # noqa: E402
from _pr690_review_fixtures import (  # noqa: E402
    ROUND2_COMMIT_SHA,
    round1_comment,
    round2_comment,
    round_reviews,
)

PR = "https://github.com/o/r/pull/7"


def _deliver(host, watch, *, env=None):
    return deliver(
        PR, project_root=Path("/tmp/wt"), run_id="iterate-2026-07-31-f11-delivery-truth",
        head_branch=HEAD, base_branch=BASE, repo=REPO, env=env or {},
        host=host, watch=watch,
    )


def test_a_red_pr_review_check_with_no_history_still_reports_checks_failed():
    """One BLOCK verdict has nothing to recur against — only a SECOND one could
    make this non-converging. The ordinary exit-2 path must survive untouched."""
    host = _Host(arm=_Proc(0), pr_views=[{"comments": [round1_comment()]}])
    result = _deliver(host, _watcher(
        {"status": "checks_failed", "failed": [{"name": "PR Review"}]}))
    assert result["exit_code"] == EXIT_CHECKS_FAILED
    assert "pr view" in host.calls  # the comments fetch did happen — just found no pair


def test_a_failing_check_other_than_pr_review_never_asks_for_comments():
    """Scope guard: this escalation only ever reads ONE gate. A flaky test suite
    failing twice in a row is an ordinary checks_failed, not non-converging."""
    host = _Host(arm=_Proc(0), pr_views=[{"comments": [round1_comment(), round2_comment()]}])
    result = _deliver(host, _watcher(
        {"status": "checks_failed", "failed": [{"name": "Python (lint + test)"}]}))
    assert result["exit_code"] == EXIT_CHECKS_FAILED
    # the pr_views queue was never touched — no second "pr view" beyond preflight
    assert host.calls.count("pr view") == 1


def test_two_recurring_pr_review_blocks_escalate_to_non_converging():
    """The acceptance case: PR #690's own round-1/round-2 BLOCK comments, replayed
    through the full ladder. Re-pushing was never going to fix round 2 — it names
    the same file and an overlapping claim as round 1."""
    host = _Host(arm=_Proc(0), pr_views=[{
        "comments": [round1_comment(), round2_comment()],
        "reviews": round_reviews(), "headRefOid": ROUND2_COMMIT_SHA,
    }])
    result = _deliver(host, _watcher(
        {"status": "checks_failed", "failed": [{"name": "PR Review"}]}))
    assert (result["status"], result["exit_code"]) == ("non_converging", EXIT_NON_CONVERGING)
    assert result["previous_verdict"]["posted_at"] == "2026-09-08T08:19:23Z"
    assert result["current_verdict"]["posted_at"] == "2026-09-08T09:13:44Z"
    assert "promote_required_layers.py" in result["previous_verdict"]["blocking_finding"]
    assert "promote_required_layers.py" in result["current_verdict"]["blocking_finding"]
    # The new comments/commits/headRefOid/reviews fetch is repo-pinned like
    # every other gh call (code-reviewer, Stage 2 — this call site was untested).
    comments_calls = [a for a in host.argv
                      if a[:2] == ["pr", "view"] and "comments,commits,headRefOid,reviews" in a]
    assert comments_calls, host.argv
    for argv in comments_calls:
        assert argv[-2:] == ["--repo", REPO], argv
        assert "comments,commits,headRefOid,reviews" in argv


def test_a_same_commit_rerun_does_not_escalate():
    """A stage-1 re-run posts a second BLOCK for the SAME commit (no
    `headRefOid` bump between the two verdicts) — the ladder must keep
    reporting the ordinary exit-2 path, not read a re-run as "re-pushing
    did not help" when nothing was re-pushed."""
    host = _Host(arm=_Proc(0), pr_views=[{
        "comments": [round1_comment(), round2_comment()],
        "commits": [{"oid": ROUND2_COMMIT_SHA, "committedDate": "2026-09-08T08:00:00Z"}],
        "headRefOid": ROUND2_COMMIT_SHA,
    }])
    result = _deliver(host, _watcher(
        {"status": "checks_failed", "failed": [{"name": "PR Review"}]}))
    assert result["exit_code"] == EXIT_CHECKS_FAILED


def test_an_unreadable_comments_list_fails_open_to_checks_failed():
    """A `gh` read that comes back empty must never manufacture a halt — it must
    also never swallow the real checks_failed verdict the ladder already has."""
    host = _Host(arm=_Proc(0), pr_views=[None])
    result = _deliver(host, _watcher(
        {"status": "checks_failed", "failed": [{"name": "PR Review"}]}))
    assert result["exit_code"] == EXIT_CHECKS_FAILED
