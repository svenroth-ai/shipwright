"""What Stage 3 could break, and now cannot
(iterate-2026-07-31-f11-delivery-truth).

Each test here corresponds to a concrete way the adversarial pass merged something it
should not have, or reported the wrong outcome for something it did. Split out of
``test_deliver_pr_self_merge.py`` for the 300-line limit, and worth its own file: these
are the assertions that stand between a delivered change and an unverified one.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))
sys.path.append(str(Path(__file__).resolve().parent))

from tools.deliver_pr import (  # noqa: E402
    EXIT_DELIVERED,
    EXIT_REFUSED,
    deliver,
)

from _pr_delivery_fakes import (  # noqa: E402
    BASE,
    HEAD,
    PROTECTED_REFUSAL,
    REPO,
    SHA,
    _Host,
    _open_pr,
    _Proc,
    _ready,
    _watcher,
)

PR = "https://github.com/o/r/pull/7"


def _unarmable_host(**kw):
    kw.setdefault("arm", _Proc(1, stderr=PROTECTED_REFUSAL))
    kw.setdefault("capability", {"allow_auto_merge": True, "base_protected": False})
    return _Host(**kw)


def _deliver(host, watch, *, env=None):
    return deliver(
        PR, project_root=Path("/tmp/wt"), run_id="iterate-2026-07-31-f11-delivery-truth",
        head_branch=HEAD, base_branch=BASE, repo=REPO, env=env or {},
        host=host, watch=watch,
    )


# --- Stage 3: mutations the suite could not previously catch --------------------

def test_a_merge_that_landed_despite_a_non_zero_exit_is_delivery():
    """`--delete-branch` used to make gh do LOCAL git surgery after the merge API call had
    already succeeded, so the merge could land and the command still fail — and the driver
    reported NOT DELIVERED for a change that was on main, telling the operator not to
    retry. The STATE is the evidence, in BOTH directions (Stage 3, HIGH)."""
    host = _unarmable_host(
        merge=_Proc(1, stderr="failed to delete local branch iterate/x"),
        pr_views=[_open_pr(), {"state": "MERGED"}])
    result = _deliver(host, _watcher(_ready()))
    assert (result["status"], result["exit_code"]) == ("merged", EXIT_DELIVERED)
    assert any("landed even though" in s for s in result["steps"])


def test_the_self_merge_never_deletes_the_local_branch():
    """gh's `--delete-branch` on a non-`--auto` merge checks out the default branch inside
    this worktree: it fails when the main clone holds that branch and succeeds
    DESTRUCTIVELY when it does not, leaving the iterate off its own branch mid-F11."""
    host = _unarmable_host(pr_views=[_open_pr(), {"state": "MERGED"}])
    _deliver(host, _watcher(_ready()))
    merge_call = next(c for c in host.calls if c.startswith("merge "))
    assert "--delete-branch" not in merge_call
    # …the remote ref is still cleaned up, after delivery is confirmed.
    assert "delete ref" in host.calls
    assert host.calls.index("delete ref") > host.calls.index(merge_call)


def test_an_unreadable_local_head_refuses_instead_of_merging():
    """`if local and pinned != local` let an unreadable local HEAD SKIP the comparison and
    merge whatever the PR head was — while the host module's own rule is that an unreadable
    fact is never a false one (Stage 3, HIGH)."""
    host = _unarmable_host(sha="")          # head_sha failed
    result = _deliver(host, _watcher(_ready(head="9" * 40)))
    assert result["exit_code"] == EXIT_REFUSED
    assert "unreadable" in result["reason"]
    assert not any(c.startswith("merge ") for c in host.calls)


def test_a_head_verified_by_an_earlier_invocation_is_re_verified_here():
    """Re-verification was keyed on "did I push inside THIS process", so a re-run after a
    red re-verification found the branch already current, never re-verified, and merged the
    very commit the previous invocation had refused (Stage 3, HIGH)."""
    head = "7" * 40
    host = _unarmable_host(sha=head, verify_ok=False)
    result = _deliver(host, _watcher(_ready(head=head)))
    assert result["exit_code"] == EXIT_REFUSED
    assert "verifier rejected" in result["reason"]
    assert any(c.startswith("verify ") for c in host.calls)
    assert not any(c.startswith("merge ") for c in host.calls)


def test_the_commit_f11_verified_needs_no_second_verification():
    """The common case must not pay for the guard: when the PR head IS the commit F11
    verified, nothing is re-verified."""
    head = "8" * 40
    host = _unarmable_host(sha=head, pr_views=[_open_pr(oid=head), {"state": "MERGED"}])
    result = deliver(
        PR, project_root=Path("/tmp/wt"), run_id="r", head_branch=HEAD, base_branch=BASE,
        repo=REPO, env={}, host=host, watch=_watcher(_ready(head=head)),
        verified_commit=head,
    )
    assert result["exit_code"] == EXIT_DELIVERED
    assert not any(c.startswith("verify ") for c in host.calls)


def test_a_base_that_moved_between_readiness_and_merge_refreshes_again():
    """The pre-merge re-read did not ask for `mergeStateStatus`, so nothing re-checked
    up-to-dateness at the MOMENT of merging — and on an unprotected base nothing forces it,
    so a branch that fell behind seconds ago would be squashed stale (Stage 3)."""
    host = _unarmable_host(pr_views=[_open_pr(**{"oid": SHA}) | {"mergeStateStatus": "BEHIND"},
                                     _open_pr(), {"state": "MERGED"}])
    result = _deliver(host, _watcher(_ready(), _ready()))
    assert result["exit_code"] == EXIT_DELIVERED
    assert any("base moved" in s for s in result["steps"])
