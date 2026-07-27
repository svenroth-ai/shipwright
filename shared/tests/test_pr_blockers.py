"""`lib.pr_blockers` — name why an open PR is not merging
(iterate-2026-07-27-name-the-blocker).

The motivating incident: PR #439 sat green for ~25 minutes — all ten check-runs
successful, PR Review successful, auto-merge armed — while the F11 watcher
returned `{"status": "pending", "timed_out": true}` three times. The cause was a
single unresolved review thread, which blocks auto-merge on its own. Neither the
check rollup nor the watcher mentioned threads, so the operator was told how long
it had waited and nothing about why.

Every signal here is either already in the payload the watcher fetches
(`mergeStateStatus`, which was being fetched and ignored) or one API call away
(review threads; the branch's required contexts). This suite pins the pure
summarisation: what counts as a named cause, and — the part that matters more —
when the answer must be "unknown" instead of "nothing is wrong".
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))

from lib import pr_blockers as pb  # noqa: E402


def _threads(*, unresolved=0, resolved=0, truncated=False) -> dict:
    nodes = [{"isResolved": True, "path": "a.py", "url": "u"} for _ in range(resolved)]
    nodes += [{"isResolved": False, "path": "b.py", "url": "u2"} for _ in range(unresolved)]
    return {"nodes": nodes, "pageInfo": {"hasNextPage": truncated}}


def _rules(*contexts: str) -> list[dict]:
    return [
        {"type": "pull_request"},
        {
            "type": "required_status_checks",
            "parameters": {"required_status_checks": [{"context": c} for c in contexts]},
        },
    ]


def _run(name, status="COMPLETED", conclusion="SUCCESS"):
    return {"__typename": "CheckRun", "name": name, "status": status, "conclusion": conclusion}


def _kinds(report) -> list[str]:
    return [c["kind"] for c in report["causes"]]


def _unknown_sources(report) -> list[str]:
    return [u["source"] for u in report["unknown"]]


# --- review threads -----------------------------------------------------------

def test_an_unresolved_thread_is_a_named_cause():
    causes, unknown = pb.thread_causes(_threads(unresolved=1, resolved=3))
    assert [c["kind"] for c in causes] == ["unresolved_review_threads"]
    assert causes[0]["count"] == 1
    assert unknown == []


def test_all_threads_resolved_is_no_cause():
    causes, unknown = pb.thread_causes(_threads(resolved=4))
    assert causes == [] and unknown == []


def test_a_truncated_page_with_nothing_unresolved_is_unknown_not_clean():
    """The false-green that pagination would otherwise create: an unresolved
    thread sitting on page 2 must never be reported as 'no unresolved threads'."""
    causes, unknown = pb.thread_causes(_threads(resolved=100, truncated=True))
    assert causes == []
    assert [u["source"] for u in unknown] == ["review_threads"]
    assert "truncat" in unknown[0]["reason"].lower()


def test_a_truncated_page_still_reports_what_it_did_find():
    causes, unknown = pb.thread_causes(_threads(unresolved=2, resolved=98, truncated=True))
    assert causes[0]["count"] == 2          # what we know
    assert [u["source"] for u in unknown] == ["review_threads"]  # and that we may not know all


def test_an_unreadable_thread_payload_is_unknown():
    causes, unknown = pb.thread_causes(None)
    assert causes == []
    assert [u["source"] for u in unknown] == ["review_threads"]


# --- required checks ----------------------------------------------------------

def test_a_required_check_absent_from_the_rollup_is_named():
    """The second half of the incident: a required check that never reported at
    all is invisible in the rollup, so 'no failing checks' reads as healthy."""
    causes, unknown = pb.required_check_causes(_rules("PR Review", "Python"), [_run("Python")])
    assert [c["kind"] for c in causes] == ["required_check_never_reported"]
    assert causes[0]["checks"] == ["PR Review"]
    assert unknown == []


def test_a_required_check_that_is_running_is_not_never_reported():
    causes, _ = pb.required_check_causes(
        _rules("Python"), [_run("Python", status="IN_PROGRESS", conclusion=None)]
    )
    assert [c["kind"] for c in causes] == ["required_check_still_running"]


def test_all_required_checks_reported_is_no_cause():
    causes, unknown = pb.required_check_causes(_rules("Python"), [_run("Python")])
    assert causes == [] and unknown == []


def test_unreadable_rules_is_unknown_never_no_missing_checks():
    """Token scope, rulesets vs classic protection, forks: any of these can make
    the rules endpoint unreadable. Reading that as 'nothing required is missing'
    would reintroduce the silence this change exists to remove."""
    causes, unknown = pb.required_check_causes(None, [_run("Python")])
    assert causes == []
    assert [u["source"] for u in unknown] == ["required_checks"]


def test_rules_without_a_required_status_check_rule_is_not_unknown():
    """A repo that genuinely requires no status checks is a definite answer, not
    a failure to read one."""
    causes, unknown = pb.required_check_causes([{"type": "pull_request"}], [_run("Python")])
    assert causes == [] and unknown == []


def test_legacy_status_contexts_count_as_reported():
    rollup = [{"__typename": "StatusContext", "context": "ci/legacy", "state": "SUCCESS"}]
    causes, _ = pb.required_check_causes(_rules("ci/legacy"), rollup)
    assert causes == []


# --- summarize ----------------------------------------------------------------

def test_blocked_merge_state_asserts_blocking():
    report = pb.summarize(
        merge_state="BLOCKED", threads=_threads(unresolved=1),
        rules=_rules("Python"), rollup=[_run("Python")],
    )
    assert report["blocking"] is True
    assert report["merge_state_status"] == "BLOCKED"
    assert "unresolved_review_threads" in _kinds(report)


def test_causes_are_reported_without_asserting_blocking_when_merge_state_disagrees():
    """An unresolved thread only blocks where the repository requires
    conversation resolution. Report it as a candidate cause; assert 'blocking'
    only when the host itself says BLOCKED."""
    report = pb.summarize(
        merge_state="CLEAN", threads=_threads(unresolved=1),
        rules=_rules("Python"), rollup=[_run("Python")],
    )
    assert report["blocking"] is False
    assert "unresolved_review_threads" in _kinds(report)


def test_a_fully_clean_pr_names_nothing_and_hides_nothing():
    report = pb.summarize(
        merge_state="CLEAN", threads=_threads(resolved=2),
        rules=_rules("Python"), rollup=[_run("Python")],
    )
    assert report["causes"] == [] and report["unknown"] == []


def test_summarize_carries_every_unknown_source_through():
    """Nothing readable at all: all three sources say so, and none of them is
    silently reported as clean."""
    report = pb.summarize(merge_state="", threads=None, rules=None, rollup=[])
    assert sorted(_unknown_sources(report)) == [
        "merge_state_status", "required_checks", "review_threads",
    ]


def test_reason_text_is_bounded():
    """Reasons quote host-supplied strings; they are diagnostics, not a channel
    for unbounded external text."""
    report = pb.summarize(
        merge_state="X" * 5000, threads=None, rules=None, rollup=[],
    )
    assert len(report["merge_state_status"]) <= pb.MAX_REASON_CHARS
    for entry in report["unknown"]:
        assert len(entry["reason"]) <= pb.MAX_REASON_CHARS


def test_an_empty_rules_list_is_unknown_not_nothing_required():
    """Found by probing the live API (see `_required_contexts`): the endpoint
    reports RULESETS. A repo on classic branch protection — or any branch with
    no ruleset — answers `[]`, which is indistinguishable from "nothing is
    required". Reading it as a clean answer would let a repo whose required
    checks live in classic protection report "no required check is missing"."""
    causes, unknown = pb.required_check_causes([], [_run("Python")])
    assert causes == []
    assert [u["source"] for u in unknown] == ["required_checks"]


# --- external code review follow-ups ------------------------------------------

def test_contexts_from_every_ruleset_rule_are_collected():
    """A branch can match several rulesets, each contributing required contexts.
    Stopping at the first `required_status_checks` rule would leave a check from
    a later ruleset unnamed when it never reports."""
    rules = _rules("Python") + [
        {"type": "required_status_checks",
         "parameters": {"required_status_checks": [{"context": "PR Review"}, {"context": "Python"}]}},
    ]
    causes, unknown = pb.required_check_causes(rules, [_run("Python")])
    assert [c["kind"] for c in causes] == ["required_check_never_reported"]
    assert causes[0]["checks"] == ["PR Review"]      # from the SECOND rule
    assert unknown == []


def test_an_unknown_host_merge_state_is_an_unknown_source():
    """`UNKNOWN` means the host has not computed mergeability yet. With clean
    threads and rules the report would otherwise read as a confident "nothing is
    wrong" while the host's own verdict is simply unavailable."""
    report = pb.summarize(
        merge_state="UNKNOWN", threads=_threads(resolved=1),
        rules=_rules("Python"), rollup=[_run("Python")],
    )
    assert report["causes"] == []
    assert [u["source"] for u in report["unknown"]] == ["merge_state_status"]


def test_a_missing_merge_state_is_also_unknown():
    report = pb.summarize(
        merge_state="", threads=_threads(resolved=1),
        rules=_rules("Python"), rollup=[_run("Python")],
    )
    assert [u["source"] for u in report["unknown"]] == ["merge_state_status"]


def test_a_known_merge_state_adds_no_unknown():
    report = pb.summarize(
        merge_state="CLEAN", threads=_threads(resolved=1),
        rules=_rules("Python"), rollup=[_run("Python")],
    )
    assert report["unknown"] == []


def test_probe_turns_a_fetch_failure_into_an_unknown_source(monkeypatch):
    """`probe` is the gh shell. A network/gh explosion inside it must surface as
    an unknown source, not propagate — the watcher's verdict does not depend on
    the diagnostic succeeding."""
    def boom(*a, **k):
        raise RuntimeError("gh died")

    monkeypatch.setattr(pb, "fetch_review_threads", boom)
    report = pb.probe(owner="o", name="n", number=1, branch="main",
                      merge_state="BLOCKED", rollup=[])

    assert report["blocking"] is True                  # the payload fact survives
    assert report["causes"] == []
    assert [u["source"] for u in report["unknown"]] == ["probe"]


def test_probe_summarises_when_both_fetches_work(monkeypatch):
    monkeypatch.setattr(pb, "fetch_review_threads", lambda *a, **k: _threads(unresolved=1))
    monkeypatch.setattr(pb, "fetch_branch_rules", lambda *a, **k: _rules("Python"))

    report = pb.probe(owner="o", name="n", number=1, branch="main",
                      merge_state="BLOCKED", rollup=[_run("Python")])

    assert _kinds(report) == ["unresolved_review_threads"]
