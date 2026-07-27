"""Reading each external reviewer's verdict, and comparing the two.

``external_review.py`` runs two independent reviewers and preserves both full
texts, but every downstream reader collapsed the pair into one status and one
integer finding count. One reviewer approving while the other calls the
approach fundamentally wrong therefore looked, downstream, like an ordinary
finding count. Two independent reviewers exist precisely so that disagreement
is noticed; averaging it away makes the second reviewer worthless.

This module makes the disagreement legible:

* :func:`parse_verdict` reads one constrained sentinel out of a reviewer's
  reply. It never infers a verdict from prose, headings, or finding
  severities — reviewer output is untrusted input, and a model that quotes the
  instruction back or argues with itself must not have a verdict picked for
  it. Anything ambiguous is :data:`UNKNOWN`.
* :func:`compare_verdicts` is the deterministic comparison, and
  :func:`summarize_reviews` produces the block the CLI emits and the marker
  stores.

Deriving the verdict from finding severities was considered and rejected: an
approving reviewer routinely files a high-severity refinement, and a rejecting
reviewer may file none at all because the objection is structural. Severity
measures individual findings; the contradiction that matters is about the
approach as a whole.
"""

from __future__ import annotations

import re
from typing import Any

__all__ = [
    "REVIEWERS",
    "SENTINEL",
    "UNAVAILABLE",
    "UNKNOWN",
    "VERDICTS",
    "compare_verdicts",
    "contradiction_block",
    "parse_verdict",
    "summarize_reviews",
    "summarize_verdict_pair",
    "verdict_for_review",
]

SENTINEL = "SHIPWRIGHT_VERDICT"

#: The two reviewers ``external_review.py`` always runs. A marker naming any
#: other pair is not a record of *this* review, so the gate does not accept it
#: — otherwise `--verdict foo=approve --verdict bar=approve` would satisfy the
#: check without either real reviewer having spoken.
REVIEWERS: tuple[str, ...] = ("gemini", "openai")

VERDICTS: tuple[str, ...] = ("approve", "revise", "reject")

#: The reviewer answered, but no single readable verdict could be taken from
#: the reply. Blocks — an unreadable verdict is not agreement.
UNKNOWN = "unknown"

#: The reviewer never answered (error / skipped provider). Distinct from
#: UNKNOWN: this is the pre-existing degraded-provider condition, not a
#: reviewer whose opinion we failed to read.
UNAVAILABLE = "unavailable"

# approve <-> reject is the only pair two ranks apart. approve/revise and
# revise/reject are differences of degree, which the finding list already
# carries; flagging them would make the signal worthless through noise.
_RANK = {"approve": 0, "revise": 1, "reject": 2}

# A sentinel LINE: the sentinel on a line of its own, which is exactly what
# the reviewer prompt asks for ("End your reply with exactly one line, and
# nothing after it"). Leading/trailing markdown punctuation is tolerated;
# anything else on the line is not.
#
# Counting sentinel LINES rather than sentinel TOKENS is deliberate. An
# earlier attempt counted the token anywhere in the reply and a real review
# broke it immediately: a reviewer whose finding quoted the sentinel
# mid-sentence, then gave its real verdict at the end, was read as UNKNOWN and
# a genuine `reject` was thrown away. A quoted mention inside prose is not a
# line, so it no longer interferes — while a reviewer that genuinely wrote two
# verdicts on two lines is still ambiguous and still reads UNKNOWN.
# Exactly the decoration AC1 licenses: emphasis, code ticks, a list marker, a
# blockquote, and whitespace. A heading marker is NOT included — a verdict is
# not a section — and neither is arbitrary punctuation.
_LINE_PREFIX = r"^[\s>*_`+\-]*"
_LINE_SUFFIX = r"[\s*_`.]*$"

# A line that PURPORTS to be the sentinel: the token opens the line, whatever
# follows. Counted first, so a malformed attempt still makes the reply
# ambiguous instead of being skipped over in favour of a later valid one.
_SENTINEL_LINE_RE = re.compile(rf"{_LINE_PREFIX}{re.escape(SENTINEL)}\b", re.IGNORECASE)

# A line that IS the sentinel: token, colon, one recognised word, nothing else.
_VERDICT_LINE_RE = re.compile(
    rf"{_LINE_PREFIX}{re.escape(SENTINEL)}[\s*_`]*:[\s*_`]*"
    rf"({'|'.join(VERDICTS)}){_LINE_SUFFIX}",
    re.IGNORECASE,
)


def parse_verdict(feedback: str | None) -> str:
    """Return the reviewer's verdict, or :data:`UNKNOWN`.

    Three conditions, all required: exactly one line of the reply *purports* to
    be a sentinel line, that line is the reply's last non-empty line, and it is
    well-formed. A missing sentinel, an unrecognised word, trailing prose after
    it, a truncated reply, or a reviewer that wrote two sentinel lines all
    yield ``UNKNOWN`` — which blocks.

    Counting *purported* sentinel lines before validating is what stops
    ``SHIPWRIGHT_VERDICT: nonsense`` followed by ``SHIPWRIGHT_VERDICT: approve``
    from reading as ``approve``: a reviewer that tried twice is ambiguous, and
    a malformed attempt must not be silently skipped in favour of a later one.
    Ambiguity is reported, never resolved by guessing, and a verdict is never
    inferred from prose, headings, or finding severities.
    """
    if not feedback:
        return UNKNOWN
    lines = [line for line in feedback.splitlines() if line.strip()]
    if not lines:
        return UNKNOWN
    if sum(1 for line in lines if _SENTINEL_LINE_RE.match(line)) != 1:
        return UNKNOWN
    last = _VERDICT_LINE_RE.match(lines[-1])
    return last.group(1).lower() if last else UNKNOWN


def verdict_for_review(review: dict[str, Any] | None) -> str:
    """Verdict for one leg of ``external_review.py``'s ``reviews`` block.

    A leg that did not succeed is :data:`UNAVAILABLE`, never ``UNKNOWN``: the
    distinction is what keeps a rate-limited provider from being treated as a
    reviewer whose verdict we could not read.
    """
    if not isinstance(review, dict):
        return UNAVAILABLE
    if review.get("status") != "success":
        return UNAVAILABLE
    return parse_verdict(review.get("feedback"))


def compare_verdicts(first: str, second: str) -> tuple[bool, bool]:
    """Return ``(contradiction_detected, comparable)``.

    Comparable iff both sides are real verdicts. A contradiction is one side
    approving while the other rejects — the ranks two apart. Symmetric by
    construction.
    """
    if first not in _RANK or second not in _RANK:
        return False, False
    return abs(_RANK[first] - _RANK[second]) >= 2, True


def contradiction_block(verdicts: dict[str, str]) -> dict[str, Any]:
    """The contradiction block, derived from a verdict mapping and nothing else.

    The **one** derivation. ``external_review.py`` builds it from a live run,
    ``mark-review-state.py`` writes it into the marker, and
    ``review_marker.evaluate_review_state`` recomputes it when reading that
    marker back. Because the reader derives rather than trusts, a marker whose
    stored block disagrees with its own verdicts cannot slip past a gate.

    ``requires_resolution`` is the single field downstream reads. It is true
    whenever the pair cannot be compared for any reason the operator could
    act on:

    * the two reviewers contradict each other;
    * a verdict could not be read — an unreadable verdict is not agreement;
    * only one of the two answered. Two independent reviewers exist so that
      disagreement gets noticed; with one reviewer it could not have been, so
      proceeding on that one review is a decision, not a default;
    * the pair is incomplete — two reviewers always run, so one recorded
      verdict means the record is malformed.

    Two exceptions, both meaning *no review happened at all* rather than
    *a review the operator should weigh*: an empty mapping, and a pair where
    neither provider answered. Both belong to the degraded-review gate, which
    already fails loudly, and double-reporting them here would only add noise.
    """
    names = sorted(verdicts)
    pairs = ", ".join(f"{n}={verdicts[n]}" for n in names)

    if not names:
        return {
            "detected": False, "comparable": False,
            "requires_resolution": False, "reason": "no reviews",
        }

    if tuple(names) != tuple(sorted(REVIEWERS)):
        return {
            "detected": False, "comparable": False, "requires_resolution": True,
            "reason": (
                f"expected verdicts from {', '.join(sorted(REVIEWERS))}, "
                f"got {len(names)}: {pairs or 'none'}"
            ),
        }

    detected, comparable = compare_verdicts(verdicts[names[0]], verdicts[names[1]])
    silent = sorted(n for n, v in verdicts.items() if v == UNAVAILABLE)
    unreadable = sorted(n for n, v in verdicts.items() if v == UNKNOWN)

    if detected:
        reason = f"reviewers contradict each other: {pairs}"
    elif len(silent) == 2:
        reason = f"neither reviewer answered: {pairs}"
    elif silent:
        reason = f"only one reviewer answered — {', '.join(silent)} did not ({pairs})"
    elif unreadable:
        reason = f"verdict could not be read for: {', '.join(unreadable)} ({pairs})"
    elif not comparable:
        reason = f"not comparable: {pairs}"
    else:
        reason = f"verdicts agree within one step: {pairs}"

    nothing_ran = len(silent) == 2
    return {
        "detected": detected,
        "comparable": comparable,
        "requires_resolution": bool(detected or (not comparable and not nothing_ran)),
        "reason": reason,
    }


def summarize_verdict_pair(verdicts: dict[str, str]) -> tuple[bool, str]:
    """``(requires_resolution, reason)`` — the two fields a gate needs."""
    block = contradiction_block(verdicts)
    return bool(block["requires_resolution"]), str(block["reason"])


def summarize_reviews(reviews: dict[str, Any]) -> dict[str, Any]:
    """Verdicts, provider statuses and the contradiction block for a
    ``reviews`` mapping as ``external_review.py`` produces it.

    Statuses ride along so an errored leg is legible as "this provider did not
    answer" rather than looking like a missing reviewer.
    """
    verdicts = {name: verdict_for_review(r) for name, r in reviews.items()}
    return {
        "verdicts": verdicts,
        "statuses": {
            name: (r.get("status") if isinstance(r, dict) else None)
            for name, r in reviews.items()
        },
        "contradiction": contradiction_block(verdicts),
    }
