"""`lib.main_health.classify` — the headline answer the two hooks act on.

@FR-01.19

Split out of `test_main_health.py`, which crossed the 300-line source budget.
The seam is real rather than arbitrary: that file pins what a single RUN and a
single COMMIT mean, this one pins what the whole branch reports — the status the
skill hooks key their exit codes on, the findings that ride alongside it, and
the conditions under which the answer must degrade rather than be believed.

The rule every test here serves: **unknown is never green.** A health check that
reads "I could not tell" as "healthy" is worse than none, because it is
believed — and reporting a problem is not the same as answering honestly, which
is why a DETECTED staleness has to change the verdict rather than annotate it.
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


def test_status_is_unknown_when_there_are_no_runs_at_all():
    report = mh.classify(commits=[{"sha": "5" * 40, "subject": "x"}], runs=[])
    assert report["status"] == "unknown"
    assert any(u["source"] == "runs" for u in report["unknown"])


def test_status_follows_the_tip_commit():
    tip, older = "6" * 40, "7" * 40
    commits = [{"sha": tip, "subject": "tip"}, {"sha": older, "subject": "older"}]
    runs = [
        _run(sha=tip, conclusion="failure", db_id=2),
        _run(sha=older, conclusion="success", db_id=1),
    ]
    assert mh.classify(commits=commits, runs=runs)["status"] == "red"


def test_a_passing_finding_class_workflow_leaves_the_status_alone():
    """The half of the old assertion that was right: only the overlap class
    decides `green` vs `red`, so a healthy scanner adds nothing."""
    tip = "8" * 40
    commits = [{"sha": tip, "subject": "tip"}]
    runs = [
        _run(sha=tip, conclusion="success", db_id=1),
        _run(sha=tip, workflow="CodeQL", conclusion="success", db_id=2),
    ]
    report = mh.classify(commits=commits, runs=runs)
    assert report["status"] == "green"
    assert {f["workflow"]: f["state"] for f in report["findings"]}["CodeQL"] == "pass"


def test_a_failing_finding_class_workflow_is_reported_AND_changes_the_status():
    """The half that was wrong. This test previously asserted `green` on a red
    CodeQL — it encoded the very defect external review round 1 found, which is
    how a bug survives a green suite: the expectation itself was mistaken."""
    tip = "8" * 40
    commits = [{"sha": tip, "subject": "tip"}]
    runs = [
        _run(sha=tip, conclusion="success", db_id=1),
        _run(sha=tip, workflow="CodeQL", conclusion="failure", db_id=2),
    ]
    report = mh.classify(commits=commits, runs=runs)
    assert report["status"] == "escalate"
    assert {f["workflow"]: f["state"] for f in report["findings"]}["CodeQL"] == "fail"


def test_a_newer_run_for_an_unknown_sha_reports_that_main_moved():
    """No extra API call buys this: the NEWEST push-to-main run belongs to a
    commit we have never heard of, so a newer commit exists. The answer is an
    observation, not a lock, and it says so."""
    tip = "9" * 40
    commits = [{"sha": tip, "subject": "tip"}]
    runs = [
        _run(sha=tip, conclusion="success", created="2026-07-28T10:00:00Z", db_id=1),
        _run(sha="0" * 40, conclusion="success", created="2026-07-28T11:00:00Z", db_id=2),
    ]
    report = mh.classify(commits=commits, runs=runs)
    assert any(u["reason"] == "main_advanced_during_check" for u in report["unknown"])


def test_runs_for_commits_merely_OLDER_than_the_window_are_not_main_moving():
    """Found by an empirical probe, not by a fixture: `gh run list` reaches far
    further back than the walked window, so "this SHA is not in the series" was
    true for every ordinary older commit and the tool cried "main advanced" on
    a perfectly quiet branch."""
    tip, older = "9" * 40, "8" * 40
    commits = [{"sha": tip, "subject": "tip"}, {"sha": older, "subject": "older"}]
    runs = [
        _run(sha=tip, created="2026-07-28T12:00:00Z", db_id=3),
        _run(sha=older, created="2026-07-28T11:00:00Z", db_id=2),
        _run(sha="7" * 40, created="2026-07-20T10:00:00Z", db_id=1),  # before the window
    ]
    report = mh.classify(commits=commits, runs=runs)
    assert not any(u["reason"] == "main_advanced_during_check"
                   for u in report["unknown"])


def test_a_detected_race_downgrades_the_answer_it_does_not_just_annotate_it():
    """External code review, round 1 (high): the race was DETECTED and reported
    and the status stayed `green`, so every caller keyed on the exit code acted
    on data we already knew was stale. Reporting a problem is not the same as
    answering honestly."""
    tip = "9" * 40
    commits = [{"sha": tip, "subject": "tip"}]
    runs = [
        _run(sha=tip, conclusion="success", created="2026-07-28T10:00:00Z", db_id=1),
        _run(sha="0" * 40, conclusion="success", created="2026-07-28T11:00:00Z", db_id=2),
    ]
    assert mh.classify(commits=commits, runs=runs)["status"] == "unknown"


def test_a_red_finding_class_workflow_gets_its_own_non_green_status():
    """AC-6 requires a card when a scanner is red. With `green` the two hooks
    say "carry on" and nobody ever reads `escalate` — so it is not the ordinary
    green path, and it is not `red` either (a finding is never an auto-repair)."""
    tip = "8" * 40
    commits = [{"sha": tip, "subject": "tip"}]
    runs = [
        _run(sha=tip, conclusion="success", db_id=1),
        _run(sha=tip, workflow="Security Scan", conclusion="failure", db_id=2),
    ]
    assert mh.classify(commits=commits, runs=runs)["status"] == "escalate"


def test_a_monitored_workflow_missing_from_the_repo_is_named_not_dropped():
    report = mh.classify(
        commits=[{"sha": "a" * 40, "subject": "tip"}],
        runs=[_run(sha="a" * 40)],
        workflow_files_present=["ci.yml"],
    )
    missing = [u for u in report["unknown"] if u["source"] == "workflow_policy"]
    assert missing, "a policy entry with no workflow file must be reported"
    assert "security.yml" in missing[0]["reason"]


def test_run_limit_is_derived_from_the_window_not_fixed():
    """A fixed 100 against 25 commits x 4 workflows truncates silently — the
    round-2 finding. The limit must be a function of what is being asked for."""
    assert mh.run_limit_for(25) >= 25 * len(mh.MONITORED_WORKFLOWS)
    assert mh.run_limit_for(50) > mh.run_limit_for(25)
