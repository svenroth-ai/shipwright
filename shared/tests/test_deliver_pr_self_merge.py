"""Rung 3 of the delivery ladder: the wait -> refresh -> re-verify -> pinned merge cycle
(iterate-2026-07-31-f11-delivery-truth).

Split out of ``test_deliver_pr.py`` to keep both files under the 300-line
source limit (constitution; the Group H audit fails an oversize file that carries no
baseline entry). The refusal paths matter as much as the happy path: this is the one place in the
pipeline that mutates a shared branch, and nine of these tests assert that nothing was
merged.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))
# APPENDED, not inserted at 0 — `shared/tests/tools/` exists, so putting this directory
# first makes `import tools.…` resolve to the TEST tools package instead of
# `shared/scripts/tools` (ADR-045, the lib/tools collision).
sys.path.append(str(Path(__file__).resolve().parent))

from tools.deliver_pr import (  # noqa: E402
    EXIT_CHECKS_FAILED,
    EXIT_CLOSED,
    EXIT_DELIVERED,
    EXIT_HOST_ERROR,
    EXIT_PENDING,
    EXIT_REFUSED,
    deliver,
)

from _pr_delivery_fakes import (  # noqa: E402
    BASE,
    HEAD,
    PROTECTED_REFUSAL,
    REPO,
    SHA,
    _behind,
    _Host,
    _open_pr,
    _Proc,
    _ready,
    _watcher,
)

PR = "https://github.com/o/r/pull/7"


def _deliver(host, watch, *, env=None):
    return deliver(
        PR, project_root=Path("/tmp/wt"), run_id="iterate-2026-07-31-f11-delivery-truth",
        head_branch=HEAD, base_branch=BASE, repo=REPO, env=env or {},
        host=host, watch=watch,
    )

# --- rung 3: deliver it here ---------------------------------------------------

def _unarmable_host(**kw):
    kw.setdefault("arm", _Proc(1, stderr=PROTECTED_REFUSAL))
    kw.setdefault("capability", {"allow_auto_merge": True, "base_protected": False})
    return _Host(**kw)


def test_a_green_current_branch_is_merged_here_and_confirmed():
    host = _unarmable_host(pr_views=[_open_pr(), {"state": "MERGED"}], sha=SHA)
    result = _deliver(host, _watcher(_ready()))
    assert (result["status"], result["exit_code"]) == ("merged", EXIT_DELIVERED)
    assert result["merged_by"] == "shipwright"
    assert any(c.startswith("merge ") for c in host.calls)


def test_the_merge_is_pinned_to_the_verified_commit():
    """The host, not this loop, enforces that nothing slipped in between."""
    host = _unarmable_host(pr_views=[_open_pr(), {"state": "MERGED"}], sha=SHA)
    _deliver(host, _watcher(_ready()))
    merge_call = next(c for c in host.calls if c.startswith("merge "))
    assert "--match-head-commit" in merge_call
    assert SHA in merge_call


def test_a_refresh_pushes_reverifies_and_waits_again_before_merging():
    """The invariant: what merges is what was verified. A refresh mid-wait creates
    a commit the F11 verifier never saw, so it is re-verified and the NEW head's
    checks must report before the merge."""
    refreshes = iter([{"ok": True, "pushed": True}, {"ok": True, "pushed": False}])
    host = _unarmable_host(pr_views=[_open_pr(oid="b" * 40), {"state": "MERGED"}],
                           sha="b" * 40)
    host.refresh = lambda *a, **k: (host.calls.append("refresh"), next(refreshes))[1]
    result = _deliver(host, _watcher(_ready(head="b" * 40), _ready(head="b" * 40)))
    assert result["exit_code"] == EXIT_DELIVERED
    # verification happened, and it happened BEFORE the merge
    assert any(c.startswith("verify ") for c in host.calls)
    assert host.calls.index("verify bbbbbb") < next(
        i for i, c in enumerate(host.calls) if c.startswith("merge "))


def test_a_red_reverification_stops_delivery_and_merges_nothing():
    host = _unarmable_host(refresh={"ok": True, "pushed": True}, verify_ok=False,
                           sha="c" * 40)
    result = _deliver(host, _watcher(_ready()))
    assert (result["status"], result["exit_code"]) == ("refused", EXIT_REFUSED)
    assert "re-verification" in result["reason"]
    assert not any(c.startswith("merge ") for c in host.calls)


def test_a_failed_refresh_stops_delivery():
    host = _unarmable_host(refresh={"ok": False, "pushed": False, "error": "source conflict"})
    result = _deliver(host, _watcher(_ready()))
    assert result["exit_code"] == EXIT_REFUSED
    assert "source conflict" in result["reason"]
    assert not any(c.startswith("merge ") for c in host.calls)


def test_a_head_that_moved_restarts_the_wait_instead_of_merging():
    """Between readiness and merge somebody pushed. Merging would deliver a commit
    nothing verified, so the loop goes round again."""
    host = _unarmable_host(pr_views=[_open_pr(oid="z" * 40),      # attempt 0: moved
                                     _open_pr(oid=SHA),           # attempt 1: matches
                                     {"state": "MERGED"}])
    result = _deliver(host, _watcher(_ready(), _ready()))
    assert result["exit_code"] == EXIT_DELIVERED
    # 4 reads: the preflight identity check, then the pre-merge re-read on each of
    # the two attempts, then the confirming read after the merge.
    assert host.calls.count("pr view") == 4


def test_a_head_that_keeps_moving_ends_pending_not_merged():
    host = _unarmable_host(pr_views=[_open_pr(oid="z" * 40)] * 3)
    result = _deliver(host, _watcher(_ready(), _ready(), _ready()))
    assert (result["status"], result["exit_code"]) == ("pending", EXIT_PENDING)
    assert not any(c.startswith("merge ") for c in host.calls)


def test_a_pr_that_is_not_this_runs_is_refused_before_any_mutation():
    """A stale PR number or a reused checkout must never let a token with merge
    rights touch somebody else's pull request — and the ARM is a mutating command:
    `--auto --squash --delete-branch` merges and deletes that branch the moment its
    checks go green. So the refusal must land before the arm, not just before the
    merge (Stage 1 review rejected the first version, which checked ~80 lines late)."""
    host = _unarmable_host(preflight=_open_pr(head="someone-elses-branch"))
    result = _deliver(host, _watcher(_ready()))
    assert result["exit_code"] == EXIT_REFUSED
    assert "head branch" in result["reason"]
    assert "arm" not in host.calls, "the arm is a mutating command and must not run"
    assert not any(c.startswith("merge ") for c in host.calls)


def test_a_pr_already_merged_is_reported_delivered_not_refused():
    """Re-run idempotency. F11 tells the operator to re-run delivery on a timeout or a
    host error, so a re-run AFTER the merge landed must not turn a delivered PR into a
    refusal — which is what an OPEN-only identity check does (Stage 1 review, follow-up)."""
    host = _unarmable_host(preflight=_open_pr(state="MERGED"))
    result = _deliver(host, _watcher(_ready()))
    assert (result["status"], result["exit_code"]) == ("merged", EXIT_DELIVERED)
    assert result["merged_by"] == "other"
    assert "arm" not in host.calls
    assert not any(c.startswith("merge ") for c in host.calls)


def test_a_pr_already_closed_unmerged_keeps_the_closed_verdict():
    host = _unarmable_host(preflight=_open_pr(state="CLOSED"))
    result = _deliver(host, _watcher(_ready()))
    assert (result["status"], result["exit_code"]) == ("closed", EXIT_CLOSED)
    assert "arm" not in host.calls


def test_a_pr_in_an_unrecognised_state_is_still_refused():
    """Terminal states are reported; anything else non-OPEN is still a refusal."""
    host = _unarmable_host(preflight=_open_pr(state="LOCKED"))
    result = _deliver(host, _watcher(_ready()))
    assert result["exit_code"] == EXIT_REFUSED
    assert "arm" not in host.calls


def test_an_unreadable_preflight_refuses_rather_than_arming_blind():
    """An unreadable identity is not a permissive one."""
    host = _unarmable_host(preflight=None)
    result = _deliver(host, _watcher(_ready()))
    assert result["exit_code"] == EXIT_HOST_ERROR
    assert "arm" not in host.calls


def test_a_pr_targeting_the_wrong_base_is_refused():
    host = _unarmable_host(preflight=_open_pr(base="release/1.0"))
    result = _deliver(host, _watcher(_ready()))
    assert result["exit_code"] == EXIT_REFUSED
    assert "targets" in result["reason"]


def test_a_host_refusal_of_the_merge_is_reported_not_swallowed():
    host = _unarmable_host(pr_views=[_open_pr()],
                           merge=_Proc(1, stderr="Head branch was modified"))
    result = _deliver(host, _watcher(_ready()))
    assert result["exit_code"] == EXIT_REFUSED
    assert "Head branch was modified" in result["reason"]


def test_a_merge_that_exits_zero_but_did_not_merge_is_not_delivery():
    """The exit code is never the proof — the state is."""
    host = _unarmable_host(pr_views=[_open_pr(), {"state": "OPEN"}])
    result = _deliver(host, _watcher(_ready()))
    assert (result["status"], result["exit_code"]) == ("refused", EXIT_REFUSED)
    assert "does not read as" in result["reason"]


def test_a_host_error_while_watching_is_exit_five_not_a_crash():
    """`watch_pr_delivery.main` mapped a gh failure to exit 5. Wrapping the watcher
    in a driver must not turn that into an unhandled RuntimeError (Stage 1 review)."""
    def exploding_watch(pr, **kwargs):
        raise RuntimeError("gh: could not resolve host")

    for host in (_Host(arm=_Proc(0)), _unarmable_host()):
        result = _deliver(host, exploding_watch)
        assert result["exit_code"] == EXIT_HOST_ERROR, host.calls
        assert "could not be read" in result["reason"]


def test_a_behind_branch_triggers_a_refresh_instead_of_waiting_forever():
    """The state readiness computes must be ACTED on. `refresh_needed` returned as
    `pending` would poll a BEHIND branch to the 1800s timeout — the very failure mode
    this ladder removes, one state over (Stage 1 review)."""
    refreshes = iter([{"ok": True, "pushed": True}, {"ok": True, "pushed": False}])
    host = _unarmable_host(pr_views=[_open_pr(oid="d" * 40), {"state": "MERGED"}],
                           sha="d" * 40)
    host.refresh = lambda *a, **k: (host.calls.append("refresh"), next(refreshes))[1]
    result = _deliver(host, _watcher(_behind(head="d" * 40), _ready(head="d" * 40)))
    assert result["exit_code"] == EXIT_DELIVERED
    assert "refresh" in host.calls
    assert any(c.startswith("verify ") for c in host.calls)


def test_a_host_that_insists_on_behind_with_nothing_to_integrate_ends_pending():
    """A disagreement we cannot explain must not be merged through, and must not spin
    either — the attempt bound turns it into an honest pending."""
    host = _unarmable_host(refresh={"ok": True, "pushed": False})
    host_sha = "e" * 40
    host._sha = host_sha
    result = _deliver(host, _watcher(_behind(head=host_sha, checks=1)))
    assert result["exit_code"] == EXIT_PENDING
    assert not any(c.startswith("merge ") for c in host.calls)


def test_an_unreadable_head_refuses_rather_than_merging_unpinned():
    """`--match-head-commit ""` would delegate the whole guarantee to the host's
    argument parsing. Refuse locally instead (Stage 1 review, minor)."""
    host = _unarmable_host(pr_views=[_open_pr()])
    result = _deliver(host, _watcher(_ready(head="")))
    assert result["exit_code"] == EXIT_REFUSED
    assert "pinned" in result["reason"]
    assert not any(c.startswith("merge ") for c in host.calls)


def test_red_checks_while_waiting_keep_the_existing_verdict():
    host = _unarmable_host()
    result = _deliver(host, _watcher({"status": "checks_failed",
                                      "failed": [{"name": "ci"}], "checks_observed": 4}))
    assert result["exit_code"] == EXIT_CHECKS_FAILED
    assert not any(c.startswith("merge ") for c in host.calls)


def test_a_pr_merged_by_someone_else_is_delivery_but_not_ours():
    host = _unarmable_host()
    result = _deliver(host, _watcher({"status": "merged", "checks_observed": 1}))
    assert result["exit_code"] == EXIT_DELIVERED
    assert result["merged_by"] == "other"
