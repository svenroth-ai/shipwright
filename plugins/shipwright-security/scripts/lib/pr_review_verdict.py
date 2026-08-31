"""Posting a review verdict — the shared best-effort side-effect both the
"nothing to review" early-exit and the normal decision path in `pr_review.py`
go through. Split out to keep that tool under the file-size guideline
(iterate-2026-08-31-pr-review-deepseek-model).

The two posting functions are taken as parameters rather than imported here
directly: callers (and their tests) monkeypatch `pr_review.post_pr_comment` /
`pr_review.post_pr_review_state` on the orchestrator module, and a local
`from pr_review_gh import ...` binding in this module would not see that
patch — Python resolves a bare name against the module that *defines* it,
not the one that re-exported it.
"""

from __future__ import annotations

import sys
from typing import Callable

from pr_review_dismiss import stamp_review_body
from pr_review_lib import _redact

__all__ = ["post_verdict"]


def post_verdict(pr_number: int, repo: str, api_key: str, body: str, decision: str,
                  summary: str, nonce: str, *,
                  post_comment_fn: Callable[[int, str, str], None],
                  post_review_state_fn: Callable[[int, str, str, str], None]) -> bool:
    """Post the comment + review state. Best-effort: a posting failure must not
    flip the gate, which reflects the review outcome (the exit code), not the
    side-effect. Shared so every fail-closed path leaves the same trail — a red
    check with no comment tells the reader nothing.

    The review-state body is stamped with this run's nonce, which is how the
    stale-verdict cleanup later recognises its OWN review among the PR's. Returns
    whether that state landed: without it there is no anchor, and cleanup that
    cannot identify itself must not guess.
    """
    # Stamped BEFORE the loop, not inside its iterable: Python builds that tuple
    # before entering the body, so a `stamp_review_body` that raised would
    # escape the try/except below — turning a passing review into exit 1 on the
    # one call in this construct that the best-effort contract does not cover.
    stamped = stamp_review_body(summary, nonce)
    state_posted = True
    # `is_state` is carried explicitly rather than compared by identity
    # (`fn is post_review_state_fn`) — with the posters now caller-supplied,
    # a caller passing the same callable for both would make that comparison
    # misattribute a comment-post failure to the state, wrongly suppressing
    # the stale-verdict cleanup on an otherwise passing review.
    for fn, call_args, what, is_state in (
        (post_comment_fn, (pr_number, repo, body), "PR comment", False),
        (post_review_state_fn, (pr_number, repo, decision, stamped), "review state", True),
    ):
        try:
            fn(*call_args)
        except Exception as e:  # noqa: BLE001
            print(_redact(f"[pr_review] failed to post {what}: {e}", api_key), file=sys.stderr)
            if is_state:
                state_posted = False
    return state_posted
