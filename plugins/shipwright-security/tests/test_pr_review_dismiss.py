"""Tests for scripts/lib/pr_review_dismiss_select.py — WHICH verdicts are ours.

A `CHANGES_REQUESTED` review is not retracted by a later `COMMENTED` one, so a
fail-closed Tier-3 verdict outlives the commit it was about and holds the pull
request at `mergeStateStatus: BLOCKED` with every check green and no open thread
(measured on PR #446: five such verdicts, six clean reviews after them). This
module decides WHICH of them are ours to clear; `pr_review_dismiss` makes the
calls.

The whole risk of that is over-reach, so most of what is pinned here is what the
selection must REFUSE to touch: a human's change-request, another bot's, another
workflow's under the same `github-actions[bot]` login, one about the commit that
is currently checked out, and any verdict whose ownership cannot be proven.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PLUGIN_ROOT / "scripts" / "lib"))

import pr_review_dismiss_select as D  # noqa: E402

from _pr_review_fixtures import (  # noqa: E402
    BOT,
    HEAD,
    NONCE,
    OLD,
    OTHER_NONCE,
    anchor as _anchor,
    crlf_body as _crlf_body,
    marked_body as _marked_body,
    review as _review,
)


# --- the marker ---------------------------------------------------------


class TestStamp:

    def test_the_body_carries_a_marker_the_selector_recognises(self):
        body = D.stamp_review_body("looks fine", NONCE)
        assert D.MARKER_RE.search(body)
        assert f"<!-- shipwright-pr-review:{NONCE} -->" in body
        assert "looks fine" in body

    def test_an_empty_summary_still_yields_a_postable_body(self):
        # `gh pr review` needs a body; an empty one would fail the post and,
        # with it, the anchor this run identifies itself by.
        body = D.stamp_review_body("", NONCE)
        assert body.strip()
        assert D.MARKER_RE.search(body)

    def test_a_marker_echoed_by_the_model_is_stripped_before_stamping(self):
        # The review body IS the model's summary, and the model reads the PR's
        # own diff. A PR that talks the model into emitting a marker-shaped
        # string would otherwise plant a second marker in our review.
        planted = f"see <!-- shipwright-pr-review:{OTHER_NONCE} --> here"
        body = D.stamp_review_body(planted, NONCE)
        assert OTHER_NONCE not in body
        assert len(D.MARKER_RE.findall(body)) == 1


# --- selection: what gets cleared ---------------------------------------


class TestSelectsStaleOwnVerdicts:

    def test_own_marked_verdict_on_a_superseded_commit_is_selected(self):
        sel = D.select_stale_verdicts(
            [_anchor(), _review(2, commit=OLD)], nonce=NONCE, head_sha=HEAD, reviewed_sha=HEAD)
        assert sel.review_ids == (2,)

    def test_several_are_selected_in_one_pass(self):
        reviews = [_anchor(), _review(2, commit=OLD), _review(3, commit="c" * 40)]
        sel = D.select_stale_verdicts(reviews, nonce=NONCE, head_sha=HEAD, reviewed_sha=HEAD)
        assert sel.review_ids == (2, 3)

    def test_an_already_dismissed_verdict_is_not_selected_again(self):
        # Idempotency without bookkeeping: GitHub reports a cleared review as
        # DISMISSED, so a re-run simply finds nothing (probe P3).
        sel = D.select_stale_verdicts(
            [_anchor(), _review(2, state="DISMISSED")], nonce=NONCE, head_sha=HEAD, reviewed_sha=HEAD)
        assert sel.review_ids == ()


class TestNeverSelects:

    def test_a_humans_change_request(self):
        # Even carrying the marker — a maintainer quoting the bot's own comment
        # into their review is the realistic way a body-text rule mis-fires.
        human = _review(2, login="svroch", kind="User", nonce=NONCE)
        sel = D.select_stale_verdicts([_anchor(), human], nonce=NONCE, head_sha=HEAD, reviewed_sha=HEAD)
        assert sel.review_ids == ()
        assert sel.skipped.get("human") == 1

    def test_another_bots_change_request(self):
        other = _review(2, login="dependabot[bot]", nonce=NONCE)
        sel = D.select_stale_verdicts([_anchor(), other], nonce=NONCE, head_sha=HEAD, reviewed_sha=HEAD)
        assert sel.review_ids == ()
        assert sel.skipped.get("other_identity") == 1

    def test_an_unmarked_verdict_under_the_same_shared_bot_login(self):
        # Every workflow in a repository posts as `github-actions[bot]`, so the
        # login proves nothing on its own. Ownership is proven by the marker or
        # not at all — which also means verdicts predating this change are left
        # alone, deliberately (AC7).
        legacy = _review(2, body="a review from before the marker shipped")
        sel = D.select_stale_verdicts([_anchor(), legacy], nonce=NONCE, head_sha=HEAD, reviewed_sha=HEAD)
        assert sel.review_ids == ()
        assert sel.skipped.get("unmarked") == 1

    def test_a_verdict_about_the_commit_that_is_current(self):
        # A block on the head is a live verdict, not a stale one.
        sel = D.select_stale_verdicts(
            [_anchor(), _review(2, commit=HEAD)], nonce=NONCE, head_sha=HEAD, reviewed_sha=HEAD)
        assert sel.review_ids == ()
        assert sel.skipped.get("current_commit") == 1

    def test_anything_at_all_when_the_head_has_moved(self):
        # A slow run on an old commit finishing after a fast run on a new one
        # must not retract the newer commit's live verdict.
        sel = D.select_stale_verdicts(
            [_anchor(commit=OLD), _review(2, commit="c" * 40)],
            nonce=NONCE, head_sha=HEAD, reviewed_sha=HEAD)
        assert sel.review_ids == ()
        assert "head" in sel.reason.lower()

    def test_anything_at_all_when_this_runs_own_review_is_not_visible(self):
        sel = D.select_stale_verdicts([_review(2)], nonce=NONCE, head_sha=HEAD, reviewed_sha=HEAD)
        assert sel.review_ids == ()
        assert sel.reason

    def test_an_anchor_that_is_not_a_bot(self):
        # A human review quoting this run's exact nonce must not become the
        # anchor whose login then licenses a sweep.
        forged = _review(1, state="COMMENTED", commit=HEAD, login="svroch",
                         kind="User", nonce=NONCE)
        sel = D.select_stale_verdicts([forged, _review(2)], nonce=NONCE,
                                      head_sha=HEAD, reviewed_sha=HEAD)
        assert sel.review_ids == ()
        # Asserting only the empty tuple would pass with the bot-guard DELETED:
        # the forged review would become the anchor and candidate #2 would then
        # fail the login test instead. Pin that no anchor was found at all.
        assert "not visible" in sel.reason


class TestNonce:

    def test_two_runs_never_share_a_nonce(self):
        assert D.new_nonce() != D.new_nonce()

    def test_the_nonce_fits_the_marker_the_selector_matches(self):
        assert D.MARKER_RE.fullmatch(
            f"<!-- shipwright-pr-review:{D.new_nonce()} -->")

    def test_it_comes_from_the_cryptographic_source(self, monkeypatch):
        # The docstring rests the anchor's safety on the nonce being
        # unguessable, and every past nonce is PUBLISHED in a review body on the
        # pull request. Swap `secrets.token_hex` for `uuid1().hex` (MAC +
        # timestamp) or `random.getrandbits` (recoverable from prior output) and
        # the two tests above stay green while the claim becomes false — so pin
        # the source, not just the shape.
        calls = []
        monkeypatch.setattr(D.secrets, "token_hex",
                            lambda n: calls.append(n) or "a" * 32)
        assert D.new_nonce() == "a" * 32
        assert calls == [16], "128 bits, from secrets"


@pytest.mark.parametrize("body", [
    "<!-- shipwright-pr-review: -->",
    "<!-- shipwright-pr-review:not-hex-at-all-not-hex-at-all-xx -->",
    "<!--shipwright-pr-review:" + "0" * 32 + "-->",
    "<!-- shipwright-pr-review:" + "0" * 31 + " -->",
    "<!-- SHIPWRIGHT-PR-REVIEW:" + "0" * 32 + " -->",
])
def test_a_near_miss_marker_does_not_count_as_ownership(body):
    # Through `_own_marker`, the function ownership is actually decided by —
    # asserting on MARKER_RE alone tests the regex, not the rule that uses it.
    assert D._own_marker({"body": body}) is None
    assert D._own_marker({"body": f"summary\n\n{body}"}) is None


class TestItProvesWhatItReviewed:
    """A review's `commit_id` is stamped when GitHub RECEIVES it, not at the
    commit whose diff was read. So `anchor.commit_id == head` alone only says
    "the head has not moved since I posted" — and a run that reviewed X while
    the head ran on to Z gets stamped Z, passes that test, and would retract a
    live verdict about the intermediate commit Y."""

    def test_a_run_that_reviewed_an_older_commit_clears_nothing(self):
        # Reviewed OLD; posted late, so GitHub stamped the review HEAD.
        sel = D.select_stale_verdicts(
            [_anchor(commit=HEAD), _review(2, commit="c" * 40)],
            nonce=NONCE, head_sha=HEAD, reviewed_sha=OLD)
        assert sel.review_ids == ()
        assert "reviewed" in sel.reason

    def test_an_unreadable_head_clears_nothing(self):
        sel = D.select_stale_verdicts(
            [_anchor(), _review(2)], nonce=NONCE, head_sha=HEAD, reviewed_sha=None)
        assert sel.review_ids == ()
        assert sel.reason


class TestOwnershipIsPositional:
    """`stamp_review_body` always puts the marker LAST. A marker anywhere else
    was quoted or echoed — and a candidate's body is written by a process we do
    not control, out of PR-authored text."""

    def test_a_quoted_marker_mid_body_is_not_ownership(self):
        echoed = _review(2, body=(f"the bot said <!-- shipwright-pr-review:{OTHER_NONCE} --> "
                                  "and I disagree"))
        sel = D.select_stale_verdicts([_anchor(), echoed], nonce=NONCE,
                                      head_sha=HEAD, reviewed_sha=HEAD)
        assert sel.review_ids == ()
        assert sel.skipped.get("unmarked") == 1

    def test_a_quoted_anchor_marker_does_not_become_the_anchor(self):
        quoted = _review(1, state="COMMENTED", commit=HEAD,
                         body=f"quoting <!-- shipwright-pr-review:{NONCE} --> mid-sentence")
        sel = D.select_stale_verdicts([quoted, _review(2)], nonce=NONCE,
                                      head_sha=HEAD, reviewed_sha=HEAD)
        assert sel.review_ids == ()
        assert "not visible" in sel.reason

    def test_a_body_as_github_actually_returns_it_is_recognised(self):
        # Every other fixture here uses bare LF. GitHub returns CRLF, and the
        # only thing that absorbs the trailing `\r` is a `.strip()` inside
        # `_own_marker` — delete it as a tidy-up and no anchor is EVER found
        # against live GitHub while all 27 ledger behaviours stay green.
        posted = _review(1, state="COMMENTED", commit=HEAD, body=_crlf_body(NONCE))
        candidate = _review(2, commit=OLD, body=_crlf_body(OTHER_NONCE))
        sel = D.select_stale_verdicts([posted, candidate], nonce=NONCE,
                                      head_sha=HEAD, reviewed_sha=HEAD)
        assert sel.review_ids == (2,), "CRLF must not cost us the anchor or the candidate"

    def test_what_stamp_review_body_produces_is_recognised(self):
        # The two halves must not drift apart: whatever the stamper writes, the
        # selector must accept as this run's own.
        posted = _review(1, state="COMMENTED", commit=HEAD,
                         body=D.stamp_review_body("looks fine", NONCE))
        sel = D.select_stale_verdicts([posted, _review(2, commit=OLD)],
                                      nonce=NONCE, head_sha=HEAD, reviewed_sha=HEAD)
        assert sel.review_ids == (2,)


class TestOneBadReviewDoesNotVoidTheSweep:

    def test_a_malformed_entry_is_counted_and_the_rest_still_clear(self):
        broken = {"id": None, "state": "CHANGES_REQUESTED", "commit_id": OLD,
                  "body": _marked_body(OTHER_NONCE),
                  "user": {"login": BOT, "type": "Bot"}}
        sel = D.select_stale_verdicts([_anchor(), broken, _review(3, commit=OLD)],
                                      nonce=NONCE, head_sha=HEAD, reviewed_sha=HEAD)
        assert sel.review_ids == (3,)
        assert sel.skipped.get("unreadable") == 1

    @pytest.mark.parametrize("user", ["unexpected", ["a"], 7],
                             ids=["string", "list", "int"])
    def test_a_non_object_user_does_not_abort_the_sweep(self, user):
        # `(review.get("user") or {}).get(...)` looks total and is not: a
        # non-dict `user` sails through the `or` and raises on `.get`, OUTSIDE
        # the narrow per-row guard. That escaped `select_stale_verdicts`
        # entirely, so the orchestrator reported "could not read this pull
        # request's reviews" and dismissed none of the valid candidates —
        # the whole sweep lost, under the wrong name.
        broken = {"id": 2, "state": "CHANGES_REQUESTED", "commit_id": OLD,
                  "body": _marked_body(OTHER_NONCE), "user": user}
        sel = D.select_stale_verdicts([_anchor(), broken, _review(3, commit=OLD)],
                                      nonce=NONCE, head_sha=HEAD, reviewed_sha=HEAD)
        assert sel.review_ids == (3,), "a valid candidate after a bad row still clears"

    def test_a_non_object_user_cannot_break_the_anchor_scan_either(self):
        # The anchor scan calls `_is_bot` too, from inside a generator with no
        # guard around it at all.
        broken = {"id": 9, "state": "COMMENTED", "commit_id": HEAD,
                  "body": _marked_body(NONCE), "user": "unexpected"}
        sel = D.select_stale_verdicts([broken, _anchor(), _review(3, commit=OLD)],
                                      nonce=NONCE, head_sha=HEAD, reviewed_sha=HEAD)
        assert sel.review_ids == (3,)
