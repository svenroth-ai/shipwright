"""`lib.main_health.attribute` — which commit broke `main`, and how sure we are.

@FR-01.19

Two definitions that a review round caught disagreeing with each other, now
pinned: **`first_bad_commit` is the OLDEST red after the last green**, and
`latest_red_commit` is a different fact reported alongside it. For a red streak
of three, repairing the newest one fixes nothing.

The other half of this file is about refusing to answer. Attribution inside a
partial data set is the failure mode that costs the most, because it names an
innocent commit with the same confidence it names a guilty one.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))

from lib import main_health as mh  # noqa: E402


def _commits(*subjects):
    """Newest-first commit series; sha is derived from the index."""
    return [
        {"sha": f"{i:040x}", "subject": s}
        for i, s in enumerate(subjects)
    ]


def _verdicts(commits, states):
    return {c["sha"]: st for c, st in zip(commits, states)}


def test_clean_anchor_gives_exact_attribution():
    commits = _commits("bad", "good")
    verdicts = _verdicts(commits, ["red", "green"])
    out = mh.attribute(commits, verdicts)
    assert out["confidence"] == "exact"
    assert out["first_bad_commit"]["sha"] == commits[0]["sha"]
    assert out["last_green_commit"]["sha"] == commits[1]["sha"]
    assert out["gaps"] == []


def test_first_bad_is_the_oldest_red_and_latest_red_is_reported_separately():
    commits = _commits("c3", "c2", "c1", "green")
    verdicts = _verdicts(commits, ["red", "red", "red", "green"])
    out = mh.attribute(commits, verdicts)
    assert out["first_bad_commit"]["sha"] == commits[2]["sha"], "oldest red after the anchor"
    assert out["latest_red_commit"]["sha"] == commits[0]["sha"]
    assert out["confidence"] == "exact"


def test_an_incomplete_commit_between_anchor_and_first_bad_downgrades_to_uncertain():
    commits = _commits("red", "no-run", "green")
    verdicts = _verdicts(commits, ["red", "incomplete", "green"])
    out = mh.attribute(commits, verdicts)
    assert out["confidence"] == "uncertain"
    assert [g["sha"] for g in out["gaps"]] == [commits[1]["sha"]]
    assert out["first_bad_commit"]["sha"] == commits[0]["sha"]


def test_a_running_commit_is_a_gap_not_a_green():
    commits = _commits("red", "running", "green")
    verdicts = _verdicts(commits, ["red", "running", "green"])
    out = mh.attribute(commits, verdicts)
    assert out["confidence"] == "uncertain"
    assert out["gaps"][0]["verdict"] == "running"


def test_no_green_anchor_in_the_window_refuses_to_attribute():
    commits = _commits("red", "red", "red")
    verdicts = _verdicts(commits, ["red", "red", "red"])
    out = mh.attribute(commits, verdicts)
    assert out["confidence"] == "none"
    assert out["reason_code"] == "no_green_anchor_in_window"
    assert out["first_bad_commit"] is None


def test_saturated_run_history_that_stops_short_is_truncated_not_attributed():
    """The round-3 finding: reruns can crowd older commits out of a saturated
    response. Saturation plus a walk that needs a commit older than the oldest
    retrieved run is not evidence — it is missing evidence."""
    commits = _commits("red", "red", "unknown-because-truncated")
    verdicts = _verdicts(commits, ["red", "red", "incomplete"])
    out = mh.attribute(
        commits, verdicts,
        saturated=True,
        oldest_run_sha=commits[1]["sha"],
    )
    assert out["confidence"] == "none"
    assert out["reason_code"] == "run_history_truncated"
    assert out["first_bad_commit"] is None


def test_saturation_that_still_covered_the_window_says_widen_not_truncated():
    """Two different refusals with two different fixes. Runs that reach the
    oldest commit in the window mean we really did look at all of it — the
    answer is 'widen the window', not 'the data was cut off'."""
    commits = _commits("red", "red", "red")
    verdicts = _verdicts(commits, ["red", "red", "red"])
    out = mh.attribute(
        commits, verdicts, saturated=True, oldest_run_sha=commits[-1]["sha"],
    )
    assert out["reason_code"] == "no_green_anchor_in_window"


def test_saturation_alone_does_not_refuse_when_the_anchor_is_inside_the_data():
    commits = _commits("red", "green", "older")
    verdicts = _verdicts(commits, ["red", "green", "green"])
    out = mh.attribute(
        commits, verdicts,
        saturated=True,
        oldest_run_sha=commits[2]["sha"],
    )
    assert out["confidence"] == "exact"


def test_a_repaired_red_further_back_is_history_not_a_diagnosis():
    """External code review, round 1 (medium): a green tip with an older red in
    the window still produced an attribution, which then spent the whole red
    path — extra API calls on a healthy branch, and a resolved failure presented
    as active. Attribution is about the tip you are building on."""
    commits = _commits("green tip", "was red", "green")
    verdicts = _verdicts(commits, ["green", "red", "green"])
    out = mh.attribute(commits, verdicts)
    assert out["first_bad_commit"] is None
    assert out["reason_code"] == "no_red_commit"


def test_a_red_below_a_still_running_tip_is_still_attributed():
    """The counter-case, so the fix above cannot be over-applied: a run in
    flight does not mean the branch is well — the red underneath it is real."""
    commits = _commits("running", "bad", "green")
    verdicts = _verdicts(commits, ["running", "red", "green"])
    out = mh.attribute(commits, verdicts)
    assert out["first_bad_commit"]["sha"] == commits[1]["sha"]


def test_a_green_tip_has_nothing_to_attribute():
    commits = _commits("green", "green")
    verdicts = _verdicts(commits, ["green", "green"])
    out = mh.attribute(commits, verdicts)
    assert out["confidence"] == "none"
    assert out["reason_code"] == "no_red_commit"
    assert out["first_bad_commit"] is None


def test_window_is_echoed_so_a_caller_can_widen_it_instead_of_guessing():
    commits = _commits("red", "red")
    verdicts = _verdicts(commits, ["red", "red"])
    out = mh.attribute(commits, verdicts)
    assert out["window"] == len(commits)


# --------------------------------------------------------------------------
# candidate partners
# --------------------------------------------------------------------------

def test_partners_refuse_when_the_pr_association_is_unavailable():
    out = mh.candidate_partners(base_sha=None, commits_between=None,
                                reason_code="pr_association_unavailable")
    assert out["commits"] is None
    assert out["reason_code"] == "pr_association_unavailable"


def test_partners_list_the_merges_the_bad_commit_never_saw():
    between = [{"sha": "1" * 40, "subject": "other merge"}]
    out = mh.candidate_partners(base_sha="0" * 40, commits_between=between)
    assert out["base_sha"] == "0" * 40
    assert out["commits"] == between
    assert out["reason_code"] is None


def test_an_empty_partner_set_is_an_answer_not_a_refusal():
    """Merged current: there were no untested-against changes. That is a real
    finding — it means the break is inside the commit itself."""
    out = mh.candidate_partners(base_sha="0" * 40, commits_between=[])
    assert out["commits"] == []
    assert out["reason_code"] is None
