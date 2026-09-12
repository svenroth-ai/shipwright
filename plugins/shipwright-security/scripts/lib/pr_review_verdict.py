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
from pr_review_lib import (
    EXIT_BLOCK, EXIT_ERROR, EXIT_OK, _redact, nothing_reviewed_summary, render_comment, safe_path,
)

__all__ = ["finish_decision", "handle_empty_diff", "handle_truncated_diff", "post_verdict"]


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


def finish_decision(pr_number: int, repo: str, api_key: str, decision: str, exit_code: int,
                     review: dict, *, nonce: str, reviewed_sha: str, state_posted: bool,
                     dismiss_fn: Callable[..., None]) -> int:
    """Unconditional decision excerpt + decision-specific follow-up; returns
    `exit_code` unchanged. Split out of `pr_review.main()` to keep that file
    under the file-size guideline (iterate-2026-09-03-pr-review-block-visibility).

    A correct block/approve/comment used to print nothing past `main()`'s
    "reviewing PR..." line — indistinguishable from a CI hang (PR #672: 4 runs
    misdiagnosed as an infra flake while the real findings sat unread in the PR
    comment). This always logs decision + exit_code + a bounded summary excerpt.

    `dismiss_fn` is taken as a parameter for the same reason `post_verdict`'s
    posters are: callers/tests monkeypatch `pr_review.dismiss_own_stale_verdicts`
    on the orchestrator module, which a local import here would not see.
    """
    summary_excerpt = str(review.get("summary", ""))[:300]
    print(_redact(
        f"[pr_review] decision={decision} exit={exit_code} — {summary_excerpt!r} "
        "(full findings posted as PR comment)", api_key), file=sys.stderr)
    if exit_code == EXIT_ERROR:
        print(f"[pr_review] unknown decision '{decision}' — treating as error.", file=sys.stderr)
    if exit_code == EXIT_OK and state_posted:
        # This run said yes, so its own earlier NOs about commits that are gone
        # must stop holding the PR. Only on a passing verdict, and never
        # allowed to change what the review earned — hence the outer guard as
        # well as the ones inside.
        try:
            dismiss_fn(pr_number, repo, nonce=nonce, reviewed_sha=reviewed_sha)
        except Exception as e:  # noqa: BLE001 — housekeeping never flips the gate
            print(_redact(f"[pr_review] stale-verdict cleanup failed: {e}", api_key),
                  file=sys.stderr)
    return exit_code


def handle_empty_diff(excluded: list[str], local_mode: bool, *,
                       post_verdict_fn: Callable[[str, str, str], None],
                       post_local_result_fn: Callable[[str, int, dict, str], int]) -> int:
    """The "nothing to review" early exit. Split out of `pr_review.main()` to
    keep that file under the file-size guideline
    (iterate-2026-09-12-pr-review-local-preflight).

    This script runs ONLY when the tier step decided the PR needs a review
    (needs-review label, sensitive path, or external contributor — an
    ordinary internal churn PR never reaches here). So a filtered diff that
    came back empty means a PR that HAD to be reviewed was handed to the
    model as nothing at all — and the system prompt answers an empty diff
    with `approve` plainly: a green required check over an unread change.
    The invariant is "the reviewer saw at least one file section" — NOT the
    narrower "everything was filtered". An empty fetch, a `gh` body with no
    `diff --git` header at all, and a fully-filtered PR are the same failure
    from the model's side, so this always fails closed rather than calling
    OpenRouter.

    `post_verdict_fn` posts the CI-mode comment + review state (never called
    in local mode, which only prints — see `pr_review_local`'s "preflight,
    never a waiver" contract); `model=` in the rendered comment names who
    reviewed, and nobody did on this branch, so it must not attribute the
    verdict to a model that was never sent anything.
    """
    summary = nothing_reviewed_summary(excluded)
    empty_body = render_comment({"decision": "block", "summary": summary},
                                model="no model — nothing was sent", truncated=False,
                                excluded_generated=excluded)
    print(f"[pr_review] {summary}", file=sys.stderr)
    if local_mode:
        return post_local_result_fn("block", EXIT_BLOCK, {"summary": summary}, empty_body)
    post_verdict_fn(empty_body, "block", summary)
    return EXIT_BLOCK


def handle_truncated_diff(reviewed, local_mode: bool, review: dict, body: str, *,
                          post_local_result_fn: Callable[[str, int, dict, str], int]) -> int:
    """A truncated diff is a PARTIAL review — the model never saw the whole
    change. Split out of `pr_review.main()` for the same reason as
    `handle_empty_diff` above.

    For a required gate on an untrusted (external/sensitive) PR, neither
    auto-passing nor trusting the partial verdict is safe: a large diff must
    not be able to BYPASS review by exceeding the size cap, so this always
    fails CLOSED (non-zero exit) rather than trusting `review`'s decision.
    Until iterate-2026-06-17-pr-review-truncation-failclosed this returned
    EXIT_OK — a silent size-bypass of the gate. The CI-mode comment + review
    state were already posted by the caller before this is reached (a
    partial review still leaves a trail); this only decides the exit path.
    """
    unseen = ", ".join(safe_path(p) for p in reviewed.omitted + reviewed.partial)
    extra = f" (+{reviewed.unidentified} unnamed)" if reviewed.unidentified else ""
    remedy = ("split the change or narrow --base/--diff-file before pushing" if local_mode
             else "apply a trusted exact-head GitHub approval, a schema-valid review "
                  "record with completed passes, and the `skip-pr-review` label; the "
                  "label alone cannot override")
    print(
        "[pr_review] diff exceeded the review limit — failing closed. Not reviewed in "
        f"full: {unseen or 'unidentifiable'}{extra}. {remedy}.", file=sys.stderr)
    if local_mode:
        return post_local_result_fn("block", EXIT_BLOCK, review, body)
    return EXIT_BLOCK
