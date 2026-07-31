"""Retract this reviewer's own superseded verdicts on a pull request.

GitHub does not let a later `COMMENTED` review retract an earlier
`CHANGES_REQUESTED` one from the same reviewer, and `dismiss_stale_reviews_on_push`
clears APPROVALS only. So a Tier-3 review that failed closed keeps the pull
request at `reviewDecision: CHANGES_REQUESTED` / `mergeStateStatus: BLOCKED`
after the commit it objected to is long gone — with every required check green
and no open review thread. Nothing on the pull request names the blocker; the
symptom is silence. Measured on PR #446: five such verdicts survived six later
clean reviews and the pull request merged only after a manual dismiss.

Which verdicts count as *ours*, and why nothing is cleared unless the
reviewed commit, the head and the review's own `commit_id` agree, is the
subject of `pr_review_dismiss_select` — this module only makes the calls.

Everything here is best-effort. The verdict is already posted and the required
check reflects the REVIEW's outcome; housekeeping that fails must say so and
change nothing else.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field

from pr_review_dismiss_select import (  # noqa: F401  (re-exported)
    MARKER_RE,
    StaleSelection,
    new_nonce,
    select_stale_verdicts,
    stamp_review_body,
)
from pr_review_gh import dismiss_pr_review, fetch_pr_head_sha, list_pr_reviews
from pr_review_render import strip_display_unsafe

__all__ = [
    "MARKER_RE", "DISMISSAL_MESSAGE", "DismissalReport", "StaleSelection",
    "dismiss_own_stale_verdicts", "new_nonce", "read_reviewed_head",
    "select_stale_verdicts", "stamp_review_body",
]

DISMISSAL_MESSAGE = (
    "Superseded by a later automated Shipwright review of commit {sha}. "
    "This verdict was about a commit that is no longer the head of this pull request."
)


@dataclass(frozen=True)
class DismissalReport:
    """What actually happened. Read by the caller only to LOG it."""

    dismissed: tuple[int, ...] = ()
    failed: tuple[tuple[int, str], ...] = ()
    reason: str = ""
    skipped: dict[str, int] = field(default_factory=dict)


def _inert(text: str) -> str:
    """Make a `gh` error safe to print into a CI log someone reads in a terminal.

    Delegates to `pr_review_render.strip_display_unsafe`, which owns the
    alphabet and pins it by enumeration. Deliberately NARROWER than `safe_path`:
    control-and-invisible only, no backtick/brace half — those exist for Markdown
    and prompt rendering, and blanking braces here would turn the `gh` JSON error
    this carries into `?"message": "Not Found"?`, i.e. the run failing to say
    what happened. The OpenRouter key needs no redaction: it never reaches `gh`.
    """
    return strip_display_unsafe(text)


def _describe(report: DismissalReport) -> str:
    parts = []
    if report.dismissed:
        parts.append("dismissed " + ", ".join(f"#{i}" for i in report.dismissed))
    if report.failed:
        parts.append("; ".join(f"could not dismiss #{i}: {e}" for i, e in report.failed))
    if report.skipped:
        parts.append("left alone: " + ", ".join(
            f"{n} {k}" for k, n in sorted(report.skipped.items())))
    if report.reason:
        parts.append(report.reason)
    # ONE choke point: every string this module emits is scrubbed here, so a
    # future producer that puts external text in  cannot render raw.
    return _inert("; ".join(parts)) or "no superseded verdict of ours was on this pull request"


def read_reviewed_head(pr_number: int, repo: str, *, log=None) -> str | None:
    """The PR's head at the moment the diff is about to be read.

    Its own function so the caller can take it in one line and so failing to
    read it is handled HERE, in the module that needs it: None makes the cleanup
    refuse, which costs housekeeping and never the review.
    """
    emit = log if log is not None else (lambda line: print(line, file=sys.stderr))
    try:
        return fetch_pr_head_sha(pr_number, repo)
    except Exception as e:  # noqa: BLE001 — a head we cannot read is simply unknown
        emit(f"[pr_review] could not read the pull request head: {_inert(e)}")
        return None


def dismiss_own_stale_verdicts(pr_number: int, repo: str, *, nonce: str,
                               reviewed_sha: str | None = None,
                               log=None) -> DismissalReport:
    """Clear this reviewer's superseded change-requests. Never raises.

    The verdict is already posted and the required check already reflects it, so
    every failure here is reported and then dropped. It is reported rather than
    swallowed because a stuck pull request that says nothing is the defect this
    function exists to remove — replacing it with a silent no-op would only move
    the silence.
    """
    emit = log if log is not None else (lambda line: print(line, file=sys.stderr))
    try:
        reviews = list_pr_reviews(pr_number, repo)
        # Head AFTER the listing: a head read that is fresher than the list can
        # only make the guard refuse, never approve on stale information.
        head_sha = fetch_pr_head_sha(pr_number, repo)
        selection = select_stale_verdicts(
            reviews, nonce=nonce, head_sha=head_sha, reviewed_sha=reviewed_sha)
    except Exception as e:  # noqa: BLE001 — subprocess, decode and shape errors alike
        report = DismissalReport(
            reason=f"could not read this pull request's reviews: {e}")
        emit(f"[pr_review] stale-verdict cleanup: {_describe(report)}")
        return report

    # Read the head once more with the candidate list already fixed. Nothing
    # here can be atomic with GitHub, and a candidate cannot BECOME current
    # while we work — the list was taken when it was already superseded. What
    # this catches is a force-push putting a candidate's commit back at the
    # head between the selection and the mutation, which would make a verdict
    # we are about to retract describe the code again.
    if selection.review_ids:
        try:
            if fetch_pr_head_sha(pr_number, repo) != str(head_sha):
                report = DismissalReport(
                    skipped=selection.skipped,
                    reason="the head moved while clearing — nothing was dismissed")
                emit(f"[pr_review] stale-verdict cleanup: {_describe(report)}")
                return report
        except Exception as e:  # noqa: BLE001 — an unconfirmable head is not a licence
            report = DismissalReport(
                skipped=selection.skipped,
                reason=f"could not re-confirm the head before clearing: {e}")
            emit(f"[pr_review] stale-verdict cleanup: {_describe(report)}")
            return report

    dismissed: list[int] = []
    failed: list[tuple[int, str]] = []
    message = DISMISSAL_MESSAGE.format(sha=str(head_sha)[:8])
    for review_id in selection.review_ids:
        try:
            dismiss_pr_review(pr_number, repo, review_id, message)
            dismissed.append(review_id)
        except Exception as e:  # noqa: BLE001 — one refusal must not stop the rest
            failed.append((review_id, str(e)))

    report = DismissalReport(
        dismissed=tuple(dismissed), failed=tuple(failed),
        reason=selection.reason, skipped=selection.skipped)
    emit(f"[pr_review] stale-verdict cleanup: {_describe(report)}")
    return report
