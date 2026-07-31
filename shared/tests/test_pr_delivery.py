"""The delivery ladder's pure decisions (iterate-2026-07-31-f11-delivery-truth).

Three questions, no `gh`, no clock, no subprocess:

* **why did arming fail** — and may that answer license merging here;
* **is this PR ready to merge** — distinguished from "still pending", which is
  what the watcher conflated it with;
* **may we merge at all** — the operator switch, read fail-closed.

The measured defect these exist for: on a base without branch protection
``gh pr merge --auto`` cannot be armed at all (`GraphQL: Pull request Protected
branch rules not configured for this branch`), F11 tolerates that fail-soft, and
then nothing merges the PR. Every iterate on such a repo ended not-delivered
after a 1800s pending-timeout — including every private repo on GitHub Free,
which cannot have rulesets at all.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))

from lib.pr_delivery import (  # noqa: E402
    ARM_ARMED,
    ARM_BLOCKED,
    ARM_SETTING_OFF,
    ARM_UNAVAILABLE,
    classify_arm_outcome,
    self_merge_allowed,
)

PROTECTED_REFUSAL = (
    "GraphQL: Pull request Protected branch rules not configured for this "
    "branch (enablePullRequestAutoMerge)"
)


def _run(name="ci", conclusion="SUCCESS", status="COMPLETED"):
    return {"__typename": "CheckRun", "name": name, "conclusion": conclusion,
            "status": status, "detailsUrl": "u"}


def _ctx(context="legacy", state="SUCCESS"):
    return {"__typename": "StatusContext", "context": context, "state": state,
            "targetUrl": "u"}


def _pr(*, merge_state="CLEAN", rollup=None, state="OPEN"):
    return {"state": state, "mergeStateStatus": merge_state,
            "statusCheckRollup": rollup if rollup is not None else []}


# --- why arming failed --------------------------------------------------------

def test_a_successful_arm_is_armed():
    assert classify_arm_outcome(0, "")["outcome"] == ARM_ARMED


def test_auto_merge_off_on_an_UNPROTECTED_base_is_structurally_unavailable():
    """Hard facts from `gh api` — no wording involved. Both false is case C."""
    out = classify_arm_outcome(1, "boom", allow_auto_merge=False, base_protected=False)
    assert out["outcome"] == ARM_UNAVAILABLE


def test_auto_merge_off_on_a_PROTECTED_base_is_not_self_merge_eligible():
    """The narrowing Stage 3 asked for. A protected base carries an intent — required
    reviews, required checks — and an iterate usually runs with the operator's own,
    possibly bypass-capable, token. "The host will refuse us" is an untested assumption
    there, and the remedy is one checkbox rather than a new authority."""
    out = classify_arm_outcome(1, "boom", allow_auto_merge=False, base_protected=True)
    assert out["outcome"] == ARM_SETTING_OFF
    assert out["outcome"] != ARM_UNAVAILABLE
    assert "Allow auto-merge" in out["reason"]


def test_an_unprotected_base_is_structurally_unavailable():
    """`protected` on the branch object is readable WITHOUT admin and covers
    rulesets AND classic branch protection — the reason the first draft's
    "no rulesets" signal was replaced (external review, HIGH)."""
    out = classify_arm_outcome(1, "boom", allow_auto_merge=True, base_protected=False)
    assert out["outcome"] == ARM_UNAVAILABLE


def test_the_hosts_own_refusal_is_enough_when_the_facts_cannot_be_read():
    """The measured message. Corroborating evidence PROMOTES to unavailable when
    both reads failed — otherwise a repo whose API calls are blocked could never
    be delivered to."""
    out = classify_arm_outcome(1, PROTECTED_REFUSAL,
                               allow_auto_merge=None, base_protected=None)
    assert out["outcome"] == ARM_UNAVAILABLE


def test_a_permissive_picture_with_an_unknown_error_stays_blocked():
    """Both facts say arming should have worked, so the failure is transient —
    today's behaviour: keep watching."""
    out = classify_arm_outcome(1, "something new from GitHub",
                               allow_auto_merge=True, base_protected=True)
    assert out["outcome"] == ARM_BLOCKED


def test_a_draft_pr_arm_failure_is_transient_not_structural():
    """Auto-merge cannot be enabled on a draft either. It must classify blocked —
    the PR becomes armable the moment it is marked ready."""
    out = classify_arm_outcome(
        1, "GraphQL: Pull request is in draft state (enablePullRequestAutoMerge)",
        allow_auto_merge=True, base_protected=True)
    assert out["outcome"] == ARM_BLOCKED


def test_an_unreadable_picture_with_an_unknown_error_never_licenses_a_merge():
    """The conservative direction. Absence of evidence is not evidence — an
    unreadable capability may not be read as "no merger can exist"."""
    out = classify_arm_outcome(1, "gh: connection reset",
                               allow_auto_merge=None, base_protected=None)
    assert out["outcome"] == ARM_BLOCKED


def test_every_outcome_names_its_reason():
    """The operator reads this line. "unavailable" alone is not a diagnosis."""
    for kwargs in (
        {"allow_auto_merge": False, "base_protected": True},
        {"allow_auto_merge": True, "base_protected": False},
        {"allow_auto_merge": True, "base_protected": True},
    ):
        out = classify_arm_outcome(1, "boom", **kwargs)
        assert out["reason"].strip(), out


# --- may we merge at all ------------------------------------------------------

def test_self_merge_is_on_by_default():
    """The operator's decision: on by default, so a repo that cannot arm still
    delivers out of the box."""
    assert self_merge_allowed({})["allowed"] is True
    assert self_merge_allowed({"SHIPWRIGHT_ITERATE_SELF_MERGE": ""})["allowed"] is True


def test_self_merge_can_be_switched_off():
    result = self_merge_allowed({"SHIPWRIGHT_ITERATE_SELF_MERGE": "0"})
    assert result["allowed"] is False
    assert result["reason"].strip()


def test_an_unusable_switch_value_fails_closed_and_names_itself():
    """A typo must not silently grant merge authority (external review)."""
    result = self_merge_allowed({"SHIPWRIGHT_ITERATE_SELF_MERGE": "maybe"})
    assert result["allowed"] is False
    assert "maybe" in result["reason"]


def test_a_campaign_never_self_merges():
    """Under a campaign the orchestrator merges each PR in turn, interleaved-serial.
    The existing defer switch keeps its meaning and outranks the new one."""
    result = self_merge_allowed({"SHIPWRIGHT_ITERATE_AUTOMERGE": "0",
                                 "SHIPWRIGHT_ITERATE_SELF_MERGE": "1"})
    assert result["allowed"] is False
    assert "campaign" in result["reason"].lower()


def test_permissive_facts_plus_a_structural_marker_stays_blocked_on_a_protected_base():
    """The hole the narrowing opened. Wording alone must not license a self-merge past a
    base that reads as protected — believing a string over a readable fact would merge
    past required reviews on an error message (external code review, HIGH security)."""
    out = classify_arm_outcome(1, PROTECTED_REFUSAL,
                               allow_auto_merge=True, base_protected=True)
    assert out["outcome"] == ARM_SETTING_OFF
    assert out["outcome"] != ARM_UNAVAILABLE


def test_a_structural_marker_still_carries_an_unprotected_or_unreadable_base():
    """Case C must keep working when only ONE fact could be read: the marker itself
    asserts the base has no protection."""
    for protected in (False, None):
        out = classify_arm_outcome(1, PROTECTED_REFUSAL,
                                   allow_auto_merge=None, base_protected=protected)
        assert out["outcome"] == ARM_UNAVAILABLE, protected
