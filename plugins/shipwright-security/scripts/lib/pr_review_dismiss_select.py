"""Deciding WHICH superseded verdicts belong to this reviewer — no I/O.

Split from `pr_review_dismiss` (which makes the calls) so each half stays inside
the source-size guideline and the rule that decides what may be dismissed can be
read on its own. That rule is the whole safety surface of the feature, so it is
worth reading without the subprocess plumbing around it.

Ownership is *proven*, never inferred:

* every review this reviewer posts carries `<!-- shipwright-pr-review:{nonce} -->`
  as the LAST line of its body;
* the **anchor** is the review carrying THIS run's nonce, so a concurrent run
  cannot become the thing we reason from;
* a candidate must carry a marker of its own — the login cannot stand in for
  that, because every workflow in a repository posts as `github-actions[bot]`
  and matching on it would sweep up other workflows' change-requests;
* a candidate must be a `Bot`, so a human who quotes this reviewer's text into
  their own review is out of reach;
* and nothing happens at all unless the commit this run REVIEWED, the pull
  request's current head, and the commit its own review is stamped with are all
  the same commit.

That last chain needs all three terms, and it is easy to think two suffice.
GitHub stamps a review's ``commit_id`` at SUBMISSION time — the head as it was
when the review landed, NOT the commit whose diff was read. So
`anchor.commit_id == head` alone says only "the head has not moved since I
posted": a run that reviewed X while the head advanced to Z is stamped Z, passes
that test, and would retract a live verdict about the intermediate commit Y.
The reviewed SHA comes in from the caller, which is what makes the guard mean
what it claims.

Verdicts posted before this shipped carry no marker and are therefore never
cleared. That is deliberate: proving ownership matters more than rescuing a
backlog which, when this was written, was empty.
"""

from __future__ import annotations

import re
import secrets
from dataclasses import dataclass, field

__all__ = ["MARKER_RE", "StaleSelection", "new_nonce", "select_stale_verdicts",
           "stamp_review_body"]

_MARKER = "<!-- shipwright-pr-review:{nonce} -->"
# A structured token, matched whole. A loose `in` test on the prefix would let a
# near-miss — or another tool's namespace — read as ownership.
MARKER_RE = re.compile(r"<!-- shipwright-pr-review:[0-9a-f]{32} -->")

_FALLBACK_BODY = "Automated Tier-3 review."


def new_nonce() -> str:
    """A per-run identifier for this reviewer's own review. 128 bits: the point
    is that a PR cannot guess it and plant a review we would then anchor on."""
    return secrets.token_hex(16)


def stamp_review_body(summary: str, nonce: str) -> str:
    """Append this run's marker to a review-state body.

    Any marker-shaped text already in ``summary`` is removed first. The body is
    the MODEL's summary, and the model reads the pull request's own diff — so a
    marker appearing in it is attacker-reachable text, not our own stamp.
    """
    clean = MARKER_RE.sub("", str(summary or "")).strip() or _FALLBACK_BODY
    return f"{clean}\n\n{_MARKER.format(nonce=nonce)}"


@dataclass(frozen=True)
class StaleSelection:
    """What to dismiss, and — when that is nothing — why."""

    review_ids: tuple[int, ...] = ()
    reason: str = ""
    skipped: dict[str, int] = field(default_factory=dict)


def _user(review: dict) -> dict:
    """The review's author object, or an empty one. `or {}` is not enough: a
    non-dict `user` would sail through it and raise on `.get`, which escapes the
    per-row guard below and aborts the whole sweep under the wrong name."""
    user = review.get("user")
    return user if isinstance(user, dict) else {}


def _is_bot(review: dict) -> bool:
    return str(_user(review).get("type") or "") == "Bot"


def _login(review: dict) -> str:
    return str(_user(review).get("login") or "")


def _own_marker(review: dict) -> str | None:
    """The marker this reviewer stamped on ``review``, or None.

    Positional, not a substring search: ``stamp_review_body`` always puts the
    marker LAST, so one found anywhere else was quoted or echoed. A candidate's
    body is written by a process we do not control — a summarising bot under the
    same `github-actions[bot]` login could repeat PR-authored text verbatim.
    The trailing ``.strip()`` is load-bearing: GitHub returns bodies with CRLF.
    """
    last = str(review.get("body") or "").rstrip().rsplit("\n", 1)[-1].strip()
    return last if MARKER_RE.fullmatch(last) else None


def select_stale_verdicts(reviews: list[dict], *, nonce: str, head_sha: str,
                          reviewed_sha: str | None) -> StaleSelection:
    """Pure: pick this reviewer's own change-requests about superseded commits.

    ``reviewed_sha`` is the head the caller actually fetched the diff at. See the
    module docstring for why the anchor's own ``commit_id`` cannot stand in for
    it. Passing None (the caller could not read it) refuses everything.

    Returns an empty selection with a stated ``reason`` rather than raising —
    "nothing to do" and "must not touch this" are both ordinary outcomes.
    """
    own = _MARKER.format(nonce=nonce)
    anchor = next(
        (r for r in reviews if _own_marker(r) == own and _is_bot(r)), None)
    if anchor is None:
        return StaleSelection(
            reason="this run's own review is not visible on the pull request yet "
                   "— no verdict was cleared")
    anchor_commit = str(anchor.get("commit_id") or "")
    head = str(head_sha or "")
    if not reviewed_sha or anchor_commit != head or str(reviewed_sha) != head:
        return StaleSelection(
            reason=f"this verdict does not describe the current head "
                   f"(reviewed {str(reviewed_sha or 'unknown')[:8]}, "
                   f"posted against {anchor_commit[:8] or 'unknown'}, "
                   f"head is {head[:8] or 'unknown'}) — nothing was cleared")

    ids: list[int] = []
    skipped: dict[str, int] = {}

    def skip(key: str) -> None:
        skipped[key] = skipped.get(key, 0) + 1

    for review in reviews:
        if str(review.get("state") or "").upper() != "CHANGES_REQUESTED":
            continue
        if not _is_bot(review):
            skip("human")
        elif _own_marker(review) is None:
            skip("unmarked")
        elif _login(review) != _login(anchor):
            skip("other_identity")
        elif str(review.get("commit_id") or "") == anchor_commit:
            # "MIGHT still describe the head", not "does" — `commit_id` records
            # when a review LANDED (see above), so it cannot prove currency.
            # The conservative side is the only safe one: clearing a same-head
            # block once a later run passes would let a verdict be re-rolled
            # away by re-running the review until it agrees. Two accepted
            # consequences, spelled out in the iterate spec §6.
            skip("current_commit")
        else:
            try:
                ids.append(int(review["id"]))
            except (TypeError, ValueError, KeyError):
                # One review of an unexpected shape must not void the whole
                # sweep — letting it escape would report every legitimate
                # dismissal as "could not read this pull request's reviews",
                # naming the wrong cause. Narrow on purpose: every guard above
                # is total for a dict, so an exception THERE is a bug in this
                # module, and swallowing it would tally every row `unreadable`
                # while the log kept saying something plausible.
                skip("unreadable")
    return StaleSelection(review_ids=tuple(ids), skipped=skipped)
