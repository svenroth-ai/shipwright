"""`lib.main_health` — which runs count, and what each commit's verdict is.

@FR-01.19

The whole self-heal design rests on one claim: *"commit P green, commit C red
⇒ C is the first bad commit."* That claim is only sound if the runs feeding it
are the runs that actually tested the commit **on `main`**. The same SHA carries
both a pull-request run and a push-to-`main` run, so without the predicate below
a green PR run silently masks a red `main` run and the attribution is worse than
guesswork — it is confidently wrong.

The second rule these tests pin: **unknown is never green.** A health check that
reads "I could not tell" as "healthy" is worse than having none, because it is
believed.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))

from lib import main_health as mh  # noqa: E402


def _run(
    *,
    workflow="CI",
    sha="a" * 40,
    conclusion="success",
    status="completed",
    event="push",
    branch="main",
    created="2026-07-28T10:00:00Z",
    db_id=1,
):
    return {
        "databaseId": db_id,
        "workflowName": workflow,
        "headSha": sha,
        "headBranch": branch,
        "event": event,
        "status": status,
        "conclusion": conclusion,
        "createdAt": created,
        "url": f"https://x/{db_id}",
    }


# --------------------------------------------------------------------------
# The monitored-run predicate
# --------------------------------------------------------------------------

def test_pr_run_for_the_same_sha_never_masks_the_main_run():
    """The finding this predicate exists for: one SHA, a green PR run and a red
    push-to-main run. Only the push run may speak for `main`."""
    sha = "b" * 40
    runs = [
        _run(sha=sha, event="pull_request", branch="feature", conclusion="success",
             created="2026-07-28T11:00:00Z", db_id=2),
        _run(sha=sha, event="push", branch="main", conclusion="failure",
             created="2026-07-28T10:00:00Z", db_id=1),
    ]
    selected = mh.select_runs(runs)
    assert list(selected) == [("CI", sha)]
    assert selected[("CI", sha)]["conclusion"] == "failure"


def test_run_on_another_branch_is_not_a_main_run():
    runs = [_run(branch="release/1.0")]
    assert mh.select_runs(runs) == {}


def test_unmonitored_workflow_is_ignored():
    runs = [_run(workflow="Some Other Workflow")]
    assert mh.select_runs(runs) == {}


def test_newest_attempt_wins_for_one_workflow_and_sha():
    sha = "c" * 40
    runs = [
        _run(sha=sha, conclusion="failure", created="2026-07-28T10:00:00Z", db_id=1),
        _run(sha=sha, conclusion="success", created="2026-07-28T12:00:00Z", db_id=9),
    ]
    selected = mh.select_runs(runs)
    assert selected[("CI", sha)]["databaseId"] == 9


def test_equal_timestamps_break_towards_the_larger_run_id():
    sha = "d" * 40
    same = "2026-07-28T10:00:00Z"
    runs = [
        _run(sha=sha, conclusion="failure", created=same, db_id=7),
        _run(sha=sha, conclusion="success", created=same, db_id=8),
    ]
    assert mh.select_runs(runs)[("CI", sha)]["databaseId"] == 8


# --------------------------------------------------------------------------
# run_state — the conclusion mapping
# --------------------------------------------------------------------------

def test_success_skipped_and_neutral_all_pass():
    for c in ("success", "skipped", "neutral"):
        assert mh.run_state(_run(conclusion=c)) == "pass"


def test_every_failing_conclusion_fails():
    for c in ("failure", "timed_out", "startup_failure", "action_required"):
        assert mh.run_state(_run(conclusion=c)) == "fail"


def test_cancelled_is_inconclusive_not_pass():
    """A cancelled run is exactly what AC-1 stops producing. Reading it as a
    pass would resurrect the bug the concurrency fix removes."""
    assert mh.run_state(_run(conclusion="cancelled")) == "inconclusive"


def test_in_progress_is_running():
    assert mh.run_state(_run(status="in_progress", conclusion=None)) == "running"


def test_completed_with_an_unrecognised_conclusion_is_inconclusive():
    assert mh.run_state(_run(conclusion="something_new")) == "inconclusive"


# --------------------------------------------------------------------------
# commit_verdict — only the health-deciding class decides
# --------------------------------------------------------------------------

def _sel(pairs):
    return {(wf, sha): _run(workflow=wf, sha=sha, **kw) for wf, sha, kw in pairs}


def test_commit_is_green_when_the_deciding_workflow_passed():
    sha = "e" * 40
    assert mh.commit_verdict(sha, _sel([("CI", sha, {"conclusion": "success"})])) == "green"


def test_a_red_finding_class_workflow_does_not_make_the_commit_red():
    """Health is the overlap-class gate. A red security scan is a finding with
    its own machinery — letting it define `main`'s health would make every
    iterate try to repair something it must not touch."""
    sha = "f" * 40
    selected = _sel([
        ("CI", sha, {"conclusion": "success"}),
        ("Security Scan", sha, {"conclusion": "failure"}),
    ])
    assert mh.commit_verdict(sha, selected) == "green"


def test_commit_is_red_when_the_deciding_workflow_failed():
    sha = "1" * 40
    assert mh.commit_verdict(sha, _sel([("CI", sha, {"conclusion": "failure"})])) == "red"


def test_commit_with_no_deciding_run_is_incomplete_never_green():
    assert mh.commit_verdict("2" * 40, {}) == "incomplete"


def test_running_deciding_run_is_running():
    sha = "3" * 40
    selected = _sel([("CI", sha, {"status": "in_progress", "conclusion": None})])
    assert mh.commit_verdict(sha, selected) == "running"


def test_a_failure_outranks_a_still_running_run():
    sha = "4" * 40
    selected = {
        ("CI", sha): _run(workflow="CI", sha=sha, conclusion="failure"),
    }
    assert mh.commit_verdict(sha, selected) == "red"


