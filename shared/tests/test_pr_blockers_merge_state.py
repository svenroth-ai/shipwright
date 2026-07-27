"""The merge state is a vocabulary, not a BLOCKED flag
(iterate-2026-07-27-merge-state-vocabulary).

Found by using the shipped watcher on a real stuck PR (#462): every required
check green, no unresolved review thread, and `mergeStateStatus: DIRTY` — the
host saying "this branch conflicts with its base". The report said "no blocker
found ... most likely still queued", because mergeStateStatus was read as a
boolean (BLOCKED or nothing) and DIRTY / BEHIND / DRAFT fell on the floor. The
same defect the module exists to prevent, inside the module itself.

The second half of this file covers the `gh` shells — the one seam every other
test mocks past, and the one where a refactor silently dropped the GraphQL query
constant while the whole suite stayed green.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib import pr_blockers as pb  # noqa: E402

from test_pr_blockers import _kinds, _rules, _run, _threads  # noqa: E402

# --- the merge state is a vocabulary, not a BLOCKED flag ----------------------
#
# Found by using the shipped watcher on a real stuck PR (#462): every required
# check green, no unresolved thread, and `mergeStateStatus: DIRTY` — the host
# saying "this branch conflicts with its base". The report said "no blocker
# found ... most likely still queued". mergeStateStatus was read as a boolean
# (BLOCKED or nothing), so DIRTY / BEHIND / DRAFT fell on the floor: the same
# defect this module exists to prevent, inside the module itself.

def _state(value):
    return pb.summarize(
        merge_state=value, threads=_threads(resolved=1),
        rules=_rules("Python"), rollup=[_run("Python")],
    )


def test_a_conflicted_branch_is_named():
    """The exact payload from PR #462."""
    report = _state("DIRTY")
    assert _kinds(report) == ["merge_state"]
    assert report["causes"][0]["state"] == "DIRTY"
    assert "conflict" in report["causes"][0]["detail"].lower()
    assert report["blocking"] is True          # GitHub cannot create the merge commit


def test_an_out_of_date_branch_is_named_but_not_asserted_blocking():
    """BEHIND only blocks where the repo requires branches to be up to date, so
    name it and let the operator judge — same posture as review threads."""
    report = _state("BEHIND")
    assert _kinds(report) == ["merge_state"]
    assert "base" in report["causes"][0]["detail"].lower()
    assert report["blocking"] is False


def test_a_draft_is_named_and_blocking():
    report = _state("DRAFT")
    assert _kinds(report) == ["merge_state"]
    assert report["blocking"] is True


def test_blocked_keeps_naming_itself_and_blocking():
    report = _state("BLOCKED")
    assert _kinds(report) == ["merge_state"]
    assert report["blocking"] is True


def test_unstable_is_named_without_claiming_it_blocks():
    """UNSTABLE means a NON-required check is red — mergeable, but worth saying."""
    report = _state("UNSTABLE")
    assert _kinds(report) == ["merge_state"]
    assert report["blocking"] is False


def test_a_mergeable_state_names_nothing():
    for value in ("CLEAN", "HAS_HOOKS"):
        report = _state(value)
        assert report["causes"] == [], value
        assert report["unknown"] == [], value
        assert report["blocking"] is False, value


def test_an_unrecognised_state_is_unknown_not_clean():
    """The guard that stops this recurring. GitHub may add a value; an enum we
    do not recognise must degrade to 'we could not tell', never to 'fine'."""
    report = _state("SOME_FUTURE_STATE")
    assert report["causes"] == []
    assert [u["source"] for u in report["unknown"]] == ["merge_state_status"]
    assert "SOME_FUTURE_STATE" in report["unknown"][0]["reason"]


def test_unknown_and_absent_states_stay_unknown():
    for value in ("UNKNOWN", "", None):
        report = _state(value)
        assert [u["source"] for u in report["unknown"]] == ["merge_state_status"], value
        assert report["causes"] == [], value


def test_the_merge_state_cause_composes_with_the_others():
    report = pb.summarize(
        merge_state="DIRTY", threads=_threads(unresolved=1),
        rules=_rules("PR Review", "Python"), rollup=[_run("Python")],
    )
    assert sorted(_kinds(report)) == [
        "merge_state", "required_check_never_reported", "unresolved_review_threads",
    ]


def test_the_rendered_line_names_a_conflict_instead_of_a_queue():
    """End of the chain: what the operator actually reads must no longer say
    'most likely still queued' for a conflicted PR."""
    import sys as _sys
    _sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts" / "tools"))
    import watch_pr_delivery as wpd

    line = wpd._render_pending({"status": "pending", "timed_out": False,
                                "blockers": _state("DIRTY")})
    assert "still queued" not in line
    assert "conflict" in line.lower()


# --- the gh shells are still wired up ----------------------------------------
#
# These two exercise the fetchers with the subprocess layer stubbed out. They
# exist because the shells are the ONE seam every other test mocks past: when a
# refactor dropped the GraphQL query constant, every test still passed and
# `fetch_review_threads` would have raised NameError on the first real call.

def test_fetch_review_threads_builds_a_complete_query(monkeypatch):
    seen = {}

    def fake(args):
        seen["args"] = args
        return {"data": {"repository": {"pullRequest": {"reviewThreads": _threads(unresolved=1)}}}}

    monkeypatch.setattr(pb, "_gh_json", fake)
    out = pb.fetch_review_threads("o", "n", 7)

    assert out is not None and out["nodes"]
    query = next(a for a in seen["args"] if a.startswith("query="))
    assert "reviewThreads" in query and "hasNextPage" in query and "isResolved" in query


def test_fetch_branch_rules_url_encodes_the_branch(monkeypatch):
    seen = {}
    monkeypatch.setattr(pb, "_gh_json", lambda args: seen.setdefault("args", args) and [])
    pb.fetch_branch_rules("o", "n", "release/1.2")
    assert "release%2F1.2" in seen["args"][-1]


# --- rendering, against REAL cause objects ------------------------------------
#
# The regression these guard was invisible because the earlier renderer tests
# hand-built cause dicts carrying only the keys they asserted on. The real
# `unresolved_review_threads` cause carries BOTH `count` and `detail`, so a
# renderer branching on "detail" in cause swallowed it. Build causes with the
# production functions, never by hand.

def _render(report):
    import sys as _sys
    _sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts" / "tools"))
    import watch_pr_delivery as wpd
    return wpd._render_pending({"status": "pending", "timed_out": False, "blockers": report})


def test_a_real_thread_cause_still_renders_as_a_count():
    report = pb.summarize(
        merge_state="CLEAN", threads=_threads(unresolved=2),
        rules=_rules("Python"), rollup=[_run("Python")],
    )
    line = _render(report)
    assert "unresolved_review_threads: 2" in line
    assert "[{" not in line          # never a raw Python list
    assert "'path'" not in line      # and never untrusted paths in the operator line


def test_the_observed_state_is_rendered_not_a_fixed_phrase():
    """AC (D). A renderer that emitted a hard-coded 'BLOCKED' plus the conflict
    detail would satisfy the conflict assertion alone, so pin the state too."""
    line = _render(_state("DIRTY"))
    assert "merge state DIRTY" in line
    assert "BLOCKED" not in line


def test_control_characters_from_the_host_never_reach_the_line():
    """A branch or path may legally carry an escape sequence."""
    evil = {"nodes": [{"isResolved": False, "path": "a\x1b[31mb.py", "line": 1}],
            "pageInfo": {"hasNextPage": False}}
    report = pb.summarize(merge_state="\x1b[2JDIRTY", threads=evil,
                          rules=_rules("Python"), rollup=[_run("Python")])
    assert "\x1b" not in _render(report)
    assert "\x1b" not in json.dumps(report)
