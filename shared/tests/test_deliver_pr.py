"""The F11 delivery ladder end to end, with the host faked
(iterate-2026-07-31-f11-delivery-truth).

The measured defect: on a base without branch protection ``gh pr merge --auto``
cannot be armed at all, F11 tolerated that fail-soft, and then nothing merged the
PR — every iterate on such a repo ended not-delivered after 1800 seconds of
watching for a merger that could not exist.

These tests drive :func:`deliver` with every host call injected, so each rung of
the ladder — and every refusal — is exercised without touching GitHub. The
refusals matter as much as the happy path: this is the one place in the pipeline
that mutates a shared branch.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))
# APPENDED, not inserted at 0 — `shared/tests/tools/` exists, so putting this
# directory first makes `import tools.deliver_pr` resolve to the TEST tools package
# instead of `shared/scripts/tools` (ADR-045, the lib/tools collision). Sibling
# fixture modules here are imported by bare name, so the directory has to be on the
# path; it just must not outrank the code under test.
sys.path.append(str(Path(__file__).resolve().parent))

from tools.deliver_pr import (  # noqa: E402
    EXIT_CHECKS_FAILED,
    EXIT_DELIVERED,
    EXIT_NO_MERGER,
    EXIT_PENDING,
    EXIT_REFUSED,
    deliver,
)
import tools.deliver_pr as deliver_pr_module

from _pr_delivery_fakes import (  # noqa: E402
    BASE,
    HEAD,
    REPO,
    PROTECTED_REFUSAL,
    SHA,
    _Host,
    _behind,
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


# --- rung 1: the host arms, nothing else changes -------------------------------

def test_an_armed_pr_is_watched_and_the_host_merges_it():
    host = _Host(arm=_Proc(0))
    result = _deliver(host, _watcher({"status": "merged"}))
    assert (result["status"], result["exit_code"]) == ("merged", EXIT_DELIVERED)
    assert result["merged_by"] == "host"
    assert "merge --squash" not in " ".join(host.calls)


def test_an_armed_pr_that_goes_red_keeps_todays_verdict():
    host = _Host(arm=_Proc(0))
    result = _deliver(host, _watcher({"status": "checks_failed", "failed": [{"name": "ci"}]}))
    assert result["exit_code"] == EXIT_CHECKS_FAILED
    assert result["merged_by"] is None


def test_the_armed_path_never_asks_for_readiness():
    """Rung 1 must be byte-for-byte today's behaviour — including not opting into
    the new terminal verdict."""
    host = _Host(arm=_Proc(0))
    watch = _watcher({"status": "merged"})
    _deliver(host, watch)
    assert watch.seen[0].get("ready_is_terminal") in (None, False)


# --- rung 2: a transient refusal keeps watching -------------------------------

def test_a_transient_arm_failure_still_just_watches():
    """Both facts say arming should have worked, so the failure may clear. That is
    today's fail-soft behaviour and it must survive."""
    host = _Host(arm=_Proc(1, stderr="GraphQL: Pull request is in draft state"))
    result = _deliver(host, _watcher({"status": "pending", "timed_out": True}))
    assert result["exit_code"] == EXIT_PENDING
    assert "merge --squash" not in " ".join(host.calls)


# --- the honest fast failure ---------------------------------------------------

def test_no_merger_and_no_permission_stops_at_once_without_waiting():
    """The whole point. Previously this waited 1800 seconds for a merger that
    cannot exist; now it says so immediately, and the watcher is never entered."""
    host = _Host(arm=_Proc(1, stderr=PROTECTED_REFUSAL),
                 capability={"allow_auto_merge": True, "base_protected": False})
    watch = _watcher({"status": "pending"})
    result = _deliver(host, watch, env={"SHIPWRIGHT_ITERATE_SELF_MERGE": "0"})
    assert (result["status"], result["exit_code"]) == ("no_merger", EXIT_NO_MERGER)
    assert watch.seen == []            # never waited
    assert "merge --squash" not in " ".join(host.calls)   # never merged
    assert "switched off" in result["reason"]


def test_an_unusable_switch_value_also_refuses_rather_than_merging():
    host = _Host(arm=_Proc(1, stderr=PROTECTED_REFUSAL),
                 capability={"allow_auto_merge": True, "base_protected": False})
    result = _deliver(host, _watcher(_ready()),
                      env={"SHIPWRIGHT_ITERATE_SELF_MERGE": "probably"})
    assert result["exit_code"] == EXIT_NO_MERGER


def test_a_campaign_neither_arms_nor_self_merges():
    """The orchestrator merges each sub-iterate PR in turn, interleaved-serial —
    a sub-iterate merging itself would break the one-PR-at-a-time invariant."""
    host = _Host()
    result = _deliver(host, _watcher({"status": "merged"}),
                      env={"SHIPWRIGHT_ITERATE_AUTOMERGE": "0"})
    assert "arm" not in host.calls
    assert result["merged_by"] == "host"


def _unarmable_host(**kw):
    """A host on which host cannot arm auto-merge, so rung 3 is reached."""
    kw.setdefault("arm", _Proc(1, stderr=PROTECTED_REFUSAL))
    kw.setdefault("capability", {"allow_auto_merge": True, "base_protected": False})
    return _Host(**kw)


def test_the_arm_uses_the_exact_flag_set_and_the_prs_own_url():
    """B4.5's flag set, pinned where it now lives. This moved out of the F11 prose
    into code (iterate-2026-07-31-f11-delivery-truth), so the guarantee moved with
    it — asserted behaviourally rather than by grepping a shell line."""
    host = _Host(arm=_Proc(0))
    _deliver(host, _watcher({"status": "merged"}))
    assert host.arm_args[:2] == ["pr", "merge"]
    assert host.arm_args[2] == PR          # the PR's own url, never cwd inference
    assert host.arm_args[3:6] == ["--auto", "--squash", "--delete-branch"]
    # …and the repository is pinned, never inferred from a remote (Stage 2, security).
    assert host.arm_args[6:] == ["--repo", REPO]


def test_every_gh_call_pins_the_repository():
    """A fork and its upstream both have a PR with head `iterate/<slug>` and base
    `main`, so branch names alone let a `--repo upstream/name` watch and a
    cwd-resolved merge act on different repositories (Stage 2, security)."""
    host = _unarmable_host(pr_views=[_open_pr(), {"state": "MERGED"}])
    _deliver(host, _watcher(_ready()))
    assert host.argv, "no gh calls recorded"
    for argv in host.argv:
        assert argv[-2:] == ["--repo", REPO], argv


def test_a_pr_in_another_repository_is_refused_even_with_matching_branches():
    host = _unarmable_host(preflight=_open_pr(repo="someone/fork"))
    result = _deliver(host, _watcher(_ready()))
    assert result["exit_code"] == EXIT_REFUSED
    assert "repository" in result["reason"]
    assert "arm" not in host.calls


def test_a_head_that_is_not_the_verified_commit_is_refused_not_pinned():
    """`--match-head-commit` pins whatever the PR head IS. If somebody else pushed to
    this branch during the wait, that is a commit the verifier never saw and no refresh
    will reconcile — `ensure_current` integrates origin/main, not origin/<branch>
    (Stage 2). Refuse rather than cheerfully pinning their work."""
    host = _unarmable_host(sha="f" * 40)          # local HEAD, what F11 verified
    result = _deliver(host, _watcher(_ready(head="9" * 40)))   # PR head: someone else's
    assert result["exit_code"] == EXIT_REFUSED
    assert "no verifier here has seen" in result["reason"]
    assert not any(c.startswith("merge ") for c in host.calls)


def test_a_pr_merged_during_the_refresh_is_delivery_not_a_refusal():
    """A human or the campaign orchestrator can merge it in the seconds the refresh
    takes. The pre-merge re-read used to run that through the OPEN-only identity check
    and abort the iterate over a PR that was merged and green (Stage 2)."""
    host = _unarmable_host(pr_views=[_open_pr(state="MERGED")])
    result = _deliver(host, _watcher(_ready()))
    assert (result["status"], result["exit_code"]) == ("merged", EXIT_DELIVERED)
    assert result["merged_by"] == "other"
    assert not any(c.startswith("merge ") for c in host.calls)


def test_the_delivery_budget_is_spent_once_not_once_per_attempt():
    """Three attempts x timeout_seconds would silently make F11's `--timeout-seconds
    1800` a 5400-second block (Stage 2). Each wait gets the REMAINING budget."""
    host = _unarmable_host(refresh={"ok": True, "pushed": False})
    watch = _watcher(_behind(head=SHA))
    clock = iter([0.0, 400.0, 900.0, 1500.0, 2000.0])
    deliver(
        PR, project_root=Path("/tmp/wt"), run_id="r", head_branch=HEAD,
        base_branch=BASE, repo=REPO, env={}, host=host, watch=watch,
        timeout_seconds=1000.0, now=lambda: next(clock),
    )
    budgets = [kw["timeout_seconds"] for kw in watch.seen]
    assert budgets == sorted(budgets, reverse=True), budgets
    assert all(b <= 1000.0 for b in budgets), budgets


def test_an_arm_failure_is_classified_never_raised():
    """Fail-soft, pinned. A missing repo setting must not break delivery for every
    future iterate — the old prose guaranteed this with `|| echo WARN`."""
    host = _Host(arm=_Proc(1, stderr="boom"))
    result = _deliver(host, _watcher({"status": "pending"}))   # must not raise
    assert result["exit_code"] == EXIT_PENDING
    assert any(step.startswith("arm: ") for step in result["steps"])


def test_main_keeps_delivered_when_post_merge_audit_cannot_start(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(deliver_pr_module, "deliver", lambda *args, **kwargs: {
        "status": "merged", "exit_code": EXIT_DELIVERED, "steps": [], "merged_by": "host",
    })
    monkeypatch.setattr(deliver_pr_module, "run_merge_compliance_audit",
                        lambda *a, **kw: {"ran": False, "detail": "OSError"})
    retired = []
    monkeypatch.setattr(deliver_pr_module, "retire_run_pointer_best_effort", lambda root, run_id: retired.append(run_id))
    assert deliver_pr_module.main([
        "--pr", PR, "--repo", REPO, "--project-root", str(tmp_path), "--run-id", "r",
        "--head-branch", HEAD, "--base-branch", BASE,
    ]) == EXIT_DELIVERED
    out = capsys.readouterr()
    assert '"ran": false' in out.out.lower()
    assert "DELIVERED" in out.err
    assert retired == ["r"]
