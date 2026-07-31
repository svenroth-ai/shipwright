"""The F11 delivery ladder, composed (iterate-2026-07-31-f11-delivery-truth).

The unit suite (``shared/tests/test_deliver_pr.py``) injects a fake watcher, so it
proves the ladder's branching but says nothing about whether the ladder, the
watcher's poll loop and the readiness rules actually FIT. This test replaces the
fake watcher with the **real** ``watch_pr_delivery.watch`` and the real
``lib.pr_readiness.readiness``, faking only ``gh``, ``git`` and the sibling scripts.

That composition is the part with a history of going wrong: PR #503 found four
gates that each had their own answer to "what did this branch change", and one was
blind for eleven paths. Here three pieces have to agree about one
``statusCheckRollup`` — the watcher's failure verdict, readiness' green verdict, and
the driver's decision to merge.

Also the `cross_component` obligation for this change: delivery now composes with
the churn/merge resolver (``ensure_current``) and with the finalization verifier.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))
# Appended, never inserted at 0: `shared/tests/tools/` would otherwise shadow
# `shared/scripts/tools` (ADR-045).
sys.path.append(str(REPO_ROOT / "shared" / "tests"))

import pytest  # noqa: E402

from _pr_delivery_fakes import (  # noqa: E402
    BASE, HEAD, PROTECTED_REFUSAL, REPO, _Host, _Proc,
)
from tools import watch_pr_delivery as wpd  # noqa: E402
from tools.deliver_pr import EXIT_DELIVERED, EXIT_NO_MERGER, deliver  # noqa: E402


pytestmark = pytest.mark.cross_plugin

PR = "https://github.com/o/r/pull/7"
FIRST_SHA = "1" * 40
REFRESHED_SHA = "2" * 40


def _check(name, *, status="COMPLETED", conclusion="SUCCESS"):
    return {"__typename": "CheckRun", "name": name, "status": status,
            "conclusion": conclusion, "detailsUrl": "u"}


def _payload(*, oid, checks, merge_state="CLEAN", state="OPEN"):
    return {"state": state, "mergeStateStatus": merge_state, "url": PR,
            "baseRefName": BASE, "headRefName": HEAD, "headRefOid": oid,
            "statusCheckRollup": list(checks)}


def _real_watch(payloads):
    """The REAL watch loop, fed a scripted sequence of gh payloads.

    ``watch.fetched`` records every poll, because *how many times it polled* is the
    only thing that distinguishes "the floor held" from "it merged the first empty
    rollup it saw" — the assertion that makes the refresh test discriminating.
    """
    queue = list(payloads)
    fetched: list[str] = []

    def fetch(pr, repo):
        if not queue:
            raise AssertionError("the watcher asked for more payloads than the test scripted "
                                 "— the implementation is not reaching a terminal verdict")
        payload = queue.pop(0) if len(queue) > 1 else queue[0]
        fetched.append(payload.get("headRefOid", "?"))
        return payload

    # An ADVANCING clock. A frozen one meant a future change that never reaches a
    # terminal verdict would spin until the CI job timeout instead of failing with a
    # readable assertion — in the very file that owns the discriminating claim (Stage 2).
    ticks = iter(range(0, 100_000, 60))

    def watch(pr, **kwargs):
        return wpd.watch(pr, fetch=fetch, sleep=lambda _: None,
                         now=lambda: float(next(ticks)),
                         **{k: v for k, v in kwargs.items() if k != "repo"},
                         repo=kwargs.get("repo"))

    watch.fetched = fetched  # type: ignore[attr-defined]
    return watch


def _run(host, watch, env=None):
    return deliver(
        PR, project_root=REPO_ROOT, run_id="iterate-2026-07-31-f11-delivery-truth",
        head_branch=HEAD, base_branch=BASE, repo=REPO, env=env or {},
        host=host, watch=watch,
    )


def test_an_unarmable_pr_is_carried_all_the_way_to_merged():
    """Arm refused for a structural reason → the real watcher polls a running check
    to green → the branch is current → merge pinned → confirmed MERGED."""
    host = _Host(
        arm=_Proc(1, stderr=PROTECTED_REFUSAL),
        capability={"allow_auto_merge": True, "base_protected": False},
        pr_views=[
            {"state": "OPEN", "headRefName": HEAD, "baseRefName": BASE,
             "headRefOid": FIRST_SHA, "url": f"https://github.com/{REPO}/pull/7"},
            {"state": "MERGED"},
        ],
        sha=FIRST_SHA,
    )
    watch = _real_watch([
        _payload(oid=FIRST_SHA, checks=[_check("ci", status="IN_PROGRESS",
                                               conclusion=None)]),
        _payload(oid=FIRST_SHA, checks=[_check("ci")]),
    ])

    result = _run(host, watch)

    assert (result["status"], result["exit_code"]) == ("merged", EXIT_DELIVERED)
    assert result["merged_by"] == "shipwright"
    # The ORDER is the composition claim: identity BEFORE the arm (the arm merges and
    # deletes a branch once green, so it is itself mutating), then the capability read,
    # the refresh, a pinned merge, and the confirming read.
    assert host.calls[:3] == ["pr view", "arm", "capability"]
    assert host.calls.index("refresh") < next(
        i for i, c in enumerate(host.calls) if c.startswith("merge "))
    merge_call = next(c for c in host.calls if c.startswith("merge "))
    assert f"--match-head-commit {FIRST_SHA}" in merge_call


def test_a_refresh_mid_wait_is_reverified_before_anything_merges():
    """The invariant the ladder could otherwise break: F11 verifies before the
    watch, so a commit created DURING the wait was never verified. Here the refresh
    pushes a new head, the verifier re-runs on it, and the new head's checks have to
    report before the merge — the empty rollup of a fresh push must not read green."""
    refreshes = iter([{"ok": True, "pushed": True}, {"ok": True, "pushed": False}])
    host = _Host(
        arm=_Proc(1, stderr=PROTECTED_REFUSAL),
        capability={"allow_auto_merge": False, "base_protected": False},
        pr_views=[
            {"state": "OPEN", "headRefName": HEAD, "baseRefName": BASE,
             "headRefOid": REFRESHED_SHA, "url": f"https://github.com/{REPO}/pull/7"},
            {"state": "MERGED"},
        ],
        sha=REFRESHED_SHA,
    )
    host.refresh = lambda *a, **k: (host.calls.append("refresh"), next(refreshes))[1]

    watch = _real_watch([
        # round 1: green on the original head, three checks reported — but the host says
        # the branch is BEHIND, so the real watcher must return the terminal
        # `refresh_needed` rather than polling a state only a refresh can clear.
        _payload(oid=FIRST_SHA, checks=[_check(n) for n in "abc"], merge_state="BEHIND"),
        # round 2 begins after the refresh push: the new head has no checks yet.
        # The floor seeded from round 1 must hold this at pending...
        _payload(oid=REFRESHED_SHA, checks=[]),
        # ...until they report again.
        _payload(oid=REFRESHED_SHA, checks=[_check(n) for n in "abc"]),
    ])

    result = _run(host, watch)

    assert result["exit_code"] == EXIT_DELIVERED
    order = host.calls
    assert "refresh" in order, "a BEHIND branch must trigger the refresh, not a wait"
    assert order.index(f"verify {REFRESHED_SHA[:6]}") < next(
        i for i, c in enumerate(order) if c.startswith("merge "))
    merge_call = next(c for c in order if c.startswith("merge "))
    assert REFRESHED_SHA in merge_call, "merged a head other than the re-verified one"

    # THE discriminating assertion. Three polls: green-on-old-head, the fresh push's
    # empty rollup (held at pending by the floor), then the checks reporting again.
    # Without the "checks do not vanish" floor the second poll would have been read
    # as green-with-zero-checks and merged an untested head — and every other
    # assertion in this test would still have passed.
    assert watch.fetched == [FIRST_SHA, REFRESHED_SHA, REFRESHED_SHA]
    assert result["checks_observed"] == 3


def test_when_no_merger_can_exist_and_we_may_not_be_one_nothing_waits():
    """The regression that started this: 1800 seconds spent watching a PR that
    nothing was ever going to merge. The real watcher must not be entered at all."""
    entered = []
    host = _Host(arm=_Proc(1, stderr=PROTECTED_REFUSAL),
                 capability={"allow_auto_merge": True, "base_protected": False})

    def watch(pr, **kwargs):
        entered.append(kwargs)
        raise AssertionError("the watcher must not be entered when no merger exists")

    result = _run(host, watch, env={"SHIPWRIGHT_ITERATE_SELF_MERGE": "0"})

    assert (result["status"], result["exit_code"]) == ("no_merger", EXIT_NO_MERGER)
    assert entered == []
    assert not any(c.startswith("merge ") for c in host.calls)


def test_an_armed_repository_still_takes_the_untouched_path():
    """Case A — this repository. Arming works, the host merges, and the ladder adds
    nothing: no capability read, no refresh, no merge command of our own."""
    host = _Host(arm=_Proc(0))
    watch = _real_watch([
        _payload(oid=FIRST_SHA, checks=[_check("ci", status="QUEUED", conclusion=None)]),
        _payload(oid=FIRST_SHA, checks=[_check("ci")], state="MERGED"),
    ])

    result = _run(host, watch)

    assert (result["status"], result["merged_by"]) == ("merged", "host")
    # One identity read, one arm, and nothing else: no capability read, no refresh, no
    # merge command of our own.
    assert host.calls == ["pr view", "arm"]
    for argv in host.argv:
        assert argv[-2:] == ["--repo", REPO], argv


def test_a_protected_base_whose_setting_is_off_is_reported_not_merged():
    """The narrowing Stage 3 asked for, end to end. A protected base carries required
    reviews and checks; an iterate usually runs with the operator's own possibly
    bypass-capable token, so "the host will refuse us" is an untested assumption. The
    remedy is one checkbox, and that is what the operator is told."""
    host = _Host(arm=_Proc(1, stderr="GraphQL: auto merge is not allowed for this repository"),
                 capability={"allow_auto_merge": False, "base_protected": True})

    def watch(pr, **kwargs):
        raise AssertionError("a protected base must not reach the self-merge wait")

    result = _run(host, watch)

    assert result["exit_code"] == EXIT_NO_MERGER
    assert "Allow auto-merge" in result["reason"]
    assert not any(c.startswith("merge ") for c in host.calls)
