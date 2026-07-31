"""The delivery ladder's two act-now verdicts on top of the watcher
(iterate-2026-07-31-f11-delivery-truth).

Split out of ``test_watch_pr_delivery.py`` to keep both files under the 300-line
source limit (constitution; the Group H audit fails an oversize file that carries no
baseline entry). `pending` conflated "checks still running" with "all green and nobody is going to
merge this", which is why an un-armable PR sat for the full 1800 seconds. `ready` and
`refresh_needed` separate them, and both are OFF by default.
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

from tools import watch_pr_delivery as wpd  # noqa: E402


def _checkrun(name, status, conclusion, url="http://x"):
    return {"__typename": "CheckRun", "name": name, "status": status,
            "conclusion": conclusion, "detailsUrl": url}


def _statusctx(context, state, url="http://x"):
    return {"__typename": "StatusContext", "context": context, "state": state,
            "targetUrl": url}

# --- the delivery ladder's fifth verdict (iterate-2026-07-31-f11-delivery-truth) ---
#
# `pending` conflated "checks still running" with "all green and nobody is going to
# merge this" — which is why an un-armable PR sat for the full 1800s. `ready`
# separates them, and is OFF by default. The first test below is the one external
# review asked for: prove the default path is unchanged over a MATRIX, rather than
# arguing it from the default value.

_MATRIX = {
    "merged": {"state": "MERGED"},
    "closed": {"state": "CLOSED"},
    "red checkrun": {"state": "OPEN",
                     "statusCheckRollup": [_checkrun("ci", "COMPLETED", "FAILURE")]},
    "red context": {"state": "OPEN", "statusCheckRollup": [_statusctx("legacy", "ERROR")]},
    "running": {"state": "OPEN",
                "statusCheckRollup": [_checkrun("ci", "IN_PROGRESS", None)]},
    "all green": {"state": "OPEN", "mergeStateStatus": "CLEAN",
                  "statusCheckRollup": [_checkrun("ci", "COMPLETED", "SUCCESS")]},
    "no checks": {"state": "OPEN", "mergeStateStatus": "CLEAN", "statusCheckRollup": []},
    "blocked": {"state": "OPEN", "mergeStateStatus": "BLOCKED", "statusCheckRollup": []},
    "behind": {"state": "OPEN", "mergeStateStatus": "BEHIND", "statusCheckRollup": []},
    "no rollup key": {"state": "OPEN"},
    "skipped only": {"state": "OPEN", "mergeStateStatus": "CLEAN",
                     "statusCheckRollup": [_checkrun("ci", "COMPLETED", "SKIPPED")]},
}

#: What the classifier answered BEFORE `ready` existed, written out by hand so the
#: assertion cannot drift with the implementation it is guarding.
_PRE_CHANGE_STATUS = {
    "merged": "merged", "closed": "closed",
    "red checkrun": "checks_failed", "red context": "checks_failed",
    "running": "pending", "all green": "pending", "no checks": "pending",
    "blocked": "pending", "behind": "pending", "no rollup key": "pending",
    "skipped only": "pending",
}


def test_the_default_path_is_byte_for_byte_what_it_was():
    """No caller that does not ask for `ready` may see any change — not in the
    verdict, not in the extra keys, not in the exit code."""
    for label, payload in _MATRIX.items():
        verdict = wpd.classify_delivery(payload)
        # The new keys and verdicts must be entirely absent, not merely unequal — an
        # `!= "ready"` after the equality above could never fire.
        assert verdict["status"] not in ("ready", "refresh_needed"), label
        assert "readiness" not in verdict and "seen_names" not in verdict, label
        assert verdict["status"] == _PRE_CHANGE_STATUS[label], label


def test_asking_for_ready_only_ever_reclassifies_a_would_be_pending():
    """The new verdict may not steal a terminal one. Anything that WAS merged /
    closed / checks_failed still is."""
    for label, payload in _MATRIX.items():
        before = wpd.classify_delivery(payload)["status"]
        after = wpd.classify_delivery(payload, ready_is_terminal=True)["status"]
        if before != "pending":
            assert after == before, label
        else:
            # The two new verdicts are both refinements OF pending — nothing else.
            assert after in ("pending", "ready", "refresh_needed"), label


def test_all_green_and_mergeable_becomes_ready_when_asked():
    verdict = wpd.classify_delivery(_MATRIX["all green"], ready_is_terminal=True)
    assert verdict["status"] == "ready"
    assert verdict["readiness"]["checks_observed"] == 1


def test_a_host_with_no_checks_is_ready_and_reports_zero():
    verdict = wpd.classify_delivery(_MATRIX["no checks"], ready_is_terminal=True)
    assert verdict["status"] == "ready"
    assert verdict["readiness"]["checks_observed"] == 0


def test_a_structurally_blocked_pr_stays_pending_with_its_reason_named():
    """BLOCKED can clear on its own — an unresolved thread gets resolved, a required
    review arrives — so waiting is right, but the reason must be named."""
    verdict = wpd.classify_delivery(_MATRIX["blocked"], ready_is_terminal=True)
    assert verdict["status"] == "pending"
    assert verdict["readiness"]["state"] == "blocked"


def test_a_behind_branch_is_terminal_because_only_a_refresh_clears_it():
    """Returning `pending` here polls a BEHIND branch to the 1800s timeout — the same
    "waiting for something that will never happen" defect this ladder removes, one
    state over. Caught by Stage 1 review: readiness computed `refresh_needed` and
    nothing acted on it."""
    verdict = wpd.classify_delivery(_MATRIX["behind"], ready_is_terminal=True)
    assert verdict["status"] == "refresh_needed"
    assert verdict["readiness"]["state"] == "refresh_needed"
    assert wpd._exit_code("refresh_needed") == 4, "mergeable-after-refresh is not merged"


def test_ready_is_never_exit_zero():
    """Mergeable is not merged. Only `merged` is delivery."""
    assert wpd._exit_code("ready") == 4
    assert wpd._exit_code("merged") == 0


def test_the_watch_loop_returns_ready_with_the_head_it_observed():
    """The driver merges PINNED to this SHA, so the verdict has to carry it."""
    payloads = [
        {"state": "OPEN", "mergeStateStatus": "UNKNOWN", "statusCheckRollup": [],
         "headRefOid": "aaa"},
        {"state": "OPEN", "mergeStateStatus": "CLEAN", "headRefOid": "bbb",
         "statusCheckRollup": [_checkrun("ci", "COMPLETED", "SUCCESS")]},
    ]
    calls = iter(payloads)
    result = wpd.watch("1", ready_is_terminal=True, fetch=lambda *_: next(calls),
                       sleep=lambda _: None, now=lambda: 0.0)
    assert result["status"] == "ready"
    assert result["head_oid"] == "bbb"


def test_checks_do_not_vanish_across_polls():
    """The refresh-push hole, at loop level. Three checks reported, then a push
    empties the rollup: that must NOT read as ready-with-zero-checks."""
    # Three checks were reported on the previous head; the refresh push replaced it
    # and the new head's rollup is not populated yet. The driver re-enters the watch
    # seeding the floor with what it already saw, which is what makes this safe.
    after_refresh_push = {"state": "OPEN", "mergeStateStatus": "CLEAN",
                          "headRefOid": "bbb", "statusCheckRollup": []}

    result = wpd.watch("1", ready_is_terminal=True, seen_names=["a", "b", "c"],
                       once=True, fetch=lambda *_: after_refresh_push,
                       sleep=lambda _: None, now=lambda: 0.0)
    assert result["status"] == "pending"
    assert result["readiness"]["state"] == "pending"
    assert "do not vanish" in result["readiness"]["reason"]


def test_the_first_poll_never_believes_an_empty_rollup():
    """An empty rollup on the first look is indistinguishable from a host that runs no
    checks, and mergeability flips to CLEAN faster than Actions creates runs. One poll
    interval must pass before "no checks" is believed (Stage 2, HIGH)."""
    empty_but_clean = {"state": "OPEN", "mergeStateStatus": "CLEAN",
                       "headRefOid": "aaa", "statusCheckRollup": []}
    polls = []

    def fetch(*_):
        polls.append(1)
        return empty_but_clean

    result = wpd.watch("1", ready_is_terminal=True, fetch=fetch,
                       sleep=lambda _: None, now=lambda: 0.0)
    assert result["status"] == "ready"
    assert len(polls) == 2, "the first poll must not be trusted with an empty rollup"


def test_the_watch_reports_the_names_it_saw_so_the_next_wait_can_seed_them():
    """The floor has to survive across watch calls — the driver re-enters after a
    refresh push and must carry the names forward, not restart from empty."""
    payload = {"state": "OPEN", "mergeStateStatus": "CLEAN", "headRefOid": "aaa",
               "statusCheckRollup": [_checkrun("ci", "COMPLETED", "SUCCESS"),
                                     _statusctx("legacy", "SUCCESS")]}
    result = wpd.watch("1", ready_is_terminal=True, fetch=lambda *_: payload,
                       sleep=lambda _: None, now=lambda: 0.0)
    assert result["seen_names"] == ["ci", "legacy"]
    assert result["checks_observed"] == 2
