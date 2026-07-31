"""Tests for pr_review_dismiss's two `gh`-facing entry points.

`dismiss_own_stale_verdicts` and `read_reviewed_head` are the halves of the
module that make calls. Both are best-effort by contract: the verdict is already
posted and the required check already reflects it, so every failure here has to
be reported and then dropped. Split from `test_pr_review_dismiss.py` (which
keeps the pure selection logic) to stay inside the source-size guideline.
"""

from __future__ import annotations

import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PLUGIN_ROOT / "scripts" / "lib"))

import pr_review_dismiss as D  # noqa: E402

from _pr_review_fixtures import (  # noqa: E402
    BOT,
    HEAD,
    NONCE,
    OLD,
    OTHER_NONCE,
    anchor as _anchor,
    marked_body as _marked_body,
    review as _review,
)

# --- orchestration: best effort, and it says what it did ----------------


def _wire(monkeypatch, *, reviews=None, head=HEAD, list_exc=None, head_exc=None,
          dismiss_exc=None):
    calls = {"dismissed": [], "messages": []}

    def fake_list(pr, repo):
        if list_exc:
            raise list_exc
        return reviews if reviews is not None else [_anchor(), _review(2)]

    heads = list(head) if isinstance(head, list) else [head]

    def fake_head(pr, repo):
        if head_exc:
            raise head_exc
        calls["head_reads"] = calls.get("head_reads", 0) + 1
        return heads[min(calls["head_reads"] - 1, len(heads) - 1)]

    def fake_dismiss(pr, repo, review_id, message):
        calls["messages"].append(message)
        if dismiss_exc and review_id == 2:
            raise dismiss_exc
        calls["dismissed"].append(review_id)

    monkeypatch.setattr(D, "list_pr_reviews", fake_list)
    monkeypatch.setattr(D, "fetch_pr_head_sha", fake_head)
    monkeypatch.setattr(D, "dismiss_pr_review", fake_dismiss)
    return calls


class TestOrchestration:

    def test_it_dismisses_and_reports(self, monkeypatch):
        calls = _wire(monkeypatch)
        log = []
        rep = D.dismiss_own_stale_verdicts(7, "o/r", nonce=NONCE, reviewed_sha=HEAD, log=log.append)
        assert calls["dismissed"] == [2]
        assert rep.dismissed == (2,)
        assert any("2" in line for line in log)

    def test_the_dismissal_message_is_ours_and_names_the_commit(self, monkeypatch):
        # The endpoint rejects a dismissal with no message (probe P6), and the
        # text must not come from the model — it is written onto the PR.
        calls = _wire(monkeypatch)
        D.dismiss_own_stale_verdicts(7, "o/r", nonce=NONCE, reviewed_sha=HEAD, log=lambda _: None)
        assert calls["messages"] and HEAD[:8] in calls["messages"][0]

    def test_a_listing_failure_is_contained_and_named(self, monkeypatch):
        _wire(monkeypatch, list_exc=RuntimeError("gh: 403"))
        log = []
        rep = D.dismiss_own_stale_verdicts(7, "o/r", nonce=NONCE, reviewed_sha=HEAD, log=log.append)
        assert rep.dismissed == ()
        assert "403" in rep.reason
        # Returning the reason is not reporting it. This function is the ONLY
        # thing that prints on this path — it never raises, so the caller's own
        # except clause does not fire — and a run that clears nothing while
        # saying nothing is the exact defect being removed.
        assert "403" in " ".join(log)

    def test_a_head_lookup_failure_is_contained_and_named(self, monkeypatch):
        _wire(monkeypatch, head_exc=RuntimeError("gh: timeout"))
        log = []
        rep = D.dismiss_own_stale_verdicts(7, "o/r", nonce=NONCE, reviewed_sha=HEAD, log=log.append)
        assert rep.dismissed == ()
        assert "timeout" in rep.reason
        assert "timeout" in " ".join(log)

    def test_one_refused_dismissal_does_not_stop_the_others(self, monkeypatch):
        reviews = [_anchor(), _review(2, commit=OLD), _review(3, commit="c" * 40)]
        calls = _wire(monkeypatch, reviews=reviews,
                      dismiss_exc=RuntimeError("gh: 422 already dismissed"))
        log = []
        rep = D.dismiss_own_stale_verdicts(7, "o/r", nonce=NONCE, reviewed_sha=HEAD, log=log.append)
        assert calls["dismissed"] == [3]
        assert rep.dismissed == (3,)
        assert rep.failed and rep.failed[0][0] == 2
        # Without this, dropping the `failed` branch of the report line leaves
        # the run announcing a clean sweep while a dismissal was refused.
        line = " ".join(log)
        assert "#2" in line and "422" in line

    def test_an_unexpected_review_shape_is_contained(self, monkeypatch):
        # A missing `user` object or a non-integer id must not raise past the
        # boundary — the verdict is already posted and the gate must not flip.
        broken = {"id": None, "state": "CHANGES_REQUESTED", "commit_id": OLD,
                  "body": _marked_body(OTHER_NONCE),
                  "user": {"login": BOT, "type": "Bot"}}
        _wire(monkeypatch, reviews=[_anchor(), broken])
        rep = D.dismiss_own_stale_verdicts(7, "o/r", nonce=NONCE, reviewed_sha=HEAD, log=lambda _: None)
        assert rep.dismissed == ()

    def test_it_says_why_when_it_dismisses_nothing(self, monkeypatch):
        # The symptom this whole run exists to answer is SILENCE.
        _wire(monkeypatch, reviews=[_anchor(), _review(2, login="svroch", kind="User")])
        log = []
        rep = D.dismiss_own_stale_verdicts(7, "o/r", nonce=NONCE, reviewed_sha=HEAD, log=log.append)
        assert rep.dismissed == ()
        assert log, "a no-op must still be reported"
        assert "human" in " ".join(log)

    def test_the_default_log_goes_to_stderr(self, monkeypatch, capsys):
        _wire(monkeypatch)
        D.dismiss_own_stale_verdicts(7, "o/r", nonce=NONCE, reviewed_sha=HEAD)
        assert capsys.readouterr().err.strip()

    def test_every_reported_line_is_scrubbed_wherever_the_text_came_from(self, monkeypatch):
        # There is ONE sanitising choke point. Pin it on both producers — the
        # per-dismissal failure list and the whole-read `reason` — because they
        # reach the log by different routes, and scrubbing at construction time
        # would leave the second one raw the day a new producer is added.
        esc = chr(27) + "[31m"
        for kwargs in ({"dismiss_exc": RuntimeError(esc + "refused")},
                       {"list_exc": RuntimeError(esc + "403")}):
            _wire(monkeypatch, **kwargs)
            log = []
            D.dismiss_own_stale_verdicts(7, "o/r", nonce=NONCE, reviewed_sha=HEAD,
                                         log=log.append)
            assert log and chr(27) not in " ".join(log)


class TestTheHeadIsReconfirmedBeforeMutating:
    """Selection and dismissal are separate API calls and can never be atomic.
    A force-push landing in between can put a candidate's commit back at the
    head, which would make a verdict we are about to retract describe the code
    again."""

    def test_a_head_that_moved_since_selection_stops_the_sweep(self, monkeypatch):
        # First read (the selection's) sees HEAD; the re-confirmation sees a
        # different commit.
        calls = _wire(monkeypatch, head=[HEAD, "e" * 40])
        log = []
        rep = D.dismiss_own_stale_verdicts(7, "o/r", nonce=NONCE, reviewed_sha=HEAD,
                                           log=log.append)
        assert calls["dismissed"] == []
        assert rep.dismissed == ()
        assert "moved" in " ".join(log)

    def test_an_unconfirmable_head_stops_the_sweep(self, monkeypatch):
        reads = {"n": 0}

        def flaky(pr, repo):
            reads["n"] += 1
            if reads["n"] == 1:
                return HEAD
            raise RuntimeError("gh: 500")

        calls = _wire(monkeypatch)
        monkeypatch.setattr(D, "fetch_pr_head_sha", flaky)
        log = []
        rep = D.dismiss_own_stale_verdicts(7, "o/r", nonce=NONCE, reviewed_sha=HEAD,
                                           log=log.append)
        assert calls["dismissed"] == []
        assert rep.dismissed == ()
        assert "500" in " ".join(log)

    def test_nothing_to_dismiss_costs_no_extra_head_read(self, monkeypatch):
        # The re-confirmation exists to protect a MUTATION. With no candidate
        # there is none, so it must not spend the call.
        calls = _wire(monkeypatch, reviews=[_anchor()])
        D.dismiss_own_stale_verdicts(7, "o/r", nonce=NONCE, reviewed_sha=HEAD,
                                     log=lambda _: None)
        assert calls["head_reads"] == 1


class TestReadReviewedHead:

    def test_it_returns_the_head(self, monkeypatch):
        monkeypatch.setattr(D, "fetch_pr_head_sha", lambda pr, repo: HEAD)
        assert D.read_reviewed_head(7, "o/r", log=lambda _: None) == HEAD

    def test_a_failure_is_none_and_is_named(self, monkeypatch):
        def boom(pr, repo):
            raise RuntimeError("gh: 502")
        monkeypatch.setattr(D, "fetch_pr_head_sha", boom)
        log = []
        assert D.read_reviewed_head(7, "o/r", log=log.append) is None
        assert "502" in " ".join(log)

    def test_control_characters_from_gh_are_made_inert(self, monkeypatch):
        # This is the one stderr sink in the tool that prints raw `gh` output,
        # and a CI log is read in a terminal.
        def boom(pr, repo):
            raise RuntimeError(chr(27) + '[31mred' + chr(27) + '[0m')
        monkeypatch.setattr(D, "fetch_pr_head_sha", boom)
        log = []
        D.read_reviewed_head(7, "o/r", log=log.append)
        assert chr(27) not in " ".join(log)
