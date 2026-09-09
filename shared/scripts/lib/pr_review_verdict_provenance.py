"""Is a `PR Review` BLOCK verdict genuine, current code? (trg-ac24ec5b, PR #690)

Split out of `pr_review_convergence.py` to keep that file under the 300-line
source limit — the same reason `lib.pr_self_merge`/`lib.pr_delivery` exist as
their own modules. This module's half of the non-converging predicate: two
preconditions added after review found a text-only claim match alone
insufficient for a TERMINAL outcome.

**Authenticity.** `pr_review.py` posts via `gh pr comment` under
`pr-review-run.yml`'s `secrets.GITHUB_TOKEN` — verified against PR #690's own
fetched comment metadata, this is the login that renders as. Login alone is
not proof of origin: this repo's OWN `pr_review_dismiss_select.py` documents
why, for the harder problem of dismissing a stale review — "every workflow in
a repository posts as `github-actions[bot]`" — and it is not hypothetical
here. `bloat-check.yml` posts PR comments under the same login, built from
`_bb.scan()`'s file-path list with no character restriction; a collaborator
naming a file so its path contains both `Shipwright PR Review` and `🔴 BLOCK`
(substring checks, unanchored) gets those bytes echoed into a real,
`github-actions`-authored, unedited comment, which is everything `is_authentic`
alone requires (doubt-reviewer, Stage 3 HIGH #1 — a concrete forgery, not the
edited-comment case Stage 2 already closed).

**Commit binding — now, and why it changed.** `verdicts_span_distinct_commits`
originally inferred a comment's commit from `commits[]`/`committedDate` (see
`_commit_as_of`), an approximation: matched to the latest commit that EXISTED
when the comment posted, not the head SHA the review job actually ran on. A
push landing mid-review binds that comment to the NEW commit, reading as "a
distinct, current commit" for what was really a stage-1 re-review of OLD
code — the exact case commit-binding exists to exclude (code-reviewer, Stage
2). Doubt-reviewer Stage 3 HIGH #2 pointed at a strictly better source
already in reach with no producer change: `pr_review.py`'s `_post_verdict`
always posts a `CHANGES_REQUESTED` review (`post_pr_review_state`) alongside
the comment (`post_pr_comment`), and GitHub stamps THAT review's own
`commit.oid` at submission — verified live against PR #690: `gh pr view 690
--json reviews` still returns both, `commit.oid` intact, `submittedAt` ~1
second after the paired comment's `createdAt`, even though #690's `commits[]`
history is gone to a later rebase. `_review_commit_oid` below correlates a
comment to its sibling review by (bot login, unedited, `CHANGES_REQUESTED`,
`submittedAt` within `_REVIEW_MATCH_WINDOW_SECONDS`) and reads its `commit.oid`
— GitHub's own record, not a guess. This closes HIGH #1 too, structurally
rather than by pattern-matching harder: `bloat-check.yml` never calls
`gh pr review`, so a forged comment has no sibling review to correlate to, and
`_bind_commit` (below) does not fall back to the timestamp guess when
`reviews` data was fetched at all — only when the whole array is empty (the
fetch itself failed) does it fall back, which is the same "never manufacture
a halt on missing data" rule this module already followed.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime

__all__ = ["is_authentic", "verdicts_span_distinct_commits"]

#: See "Authenticity" above.
_BOT_AUTHOR_LOGIN = "github-actions"

#: How far a `CHANGES_REQUESTED` review's `submittedAt` may drift from its
#: sibling comment's `createdAt` and still count as the SAME `_post_verdict`
#: call. PR #690's real pair drifted ~1 second; this is generous CI-job
#: scheduling margin, not a tuned-to-the-data threshold, and it is tight
#: enough that #690's two rounds (~54 minutes apart) can never cross-match.
_REVIEW_MATCH_WINDOW_SECONDS = 300


def is_authentic(comment: Mapping) -> bool:
    """Only the real Tier-3 reviewer's own, UNEDITED comments count as verdicts.

    A matching `author.login` is not proof the BODY is what the bot wrote —
    on GitHub, a user with write access can edit another author's comment
    (code-reviewer, Stage 2), the same denial-of-delivery risk from a
    higher-privileged actor. `includesCreatedEdit` is already present on
    every element of the `gh pr view --json comments` payload this reads, so
    checking it costs no extra call. Login+edit-state alone is still not
    proof of ORIGIN (see "Authenticity" above) — that gap is closed
    separately, structurally, in `verdicts_span_distinct_commits`, so this
    function stays the same pure per-comment text/metadata check every
    caller (including `two_most_recent_block_verdicts`, which has no
    `reviews` data) already relies on.
    """
    author = comment.get("author")
    login = str((author or {}).get("login") or "") if isinstance(author, Mapping) else ""
    return login == _BOT_AUTHOR_LOGIN and not comment.get("includesCreatedEdit")


def _parse_timestamp(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _commit_as_of(commits: Sequence[Mapping], when: str) -> str:
    """FALLBACK ONLY (see module docstring) — the oid of the most recent
    commit committed at or before ``when``, or ``""``. Ties (same
    `committedDate`) break by ARRAY ORDER, not oid text: `gh pr view --json
    commits` returns commits chronologically, so array position is a real
    signal or ordering and an oid's lexical value is not (code-reviewer,
    Stage 2 missed this; doubt-reviewer, Stage 3 LOW). The BINDING itself
    remains an approximation, not a guarantee: a comment is matched to the
    latest commit that existed when it was posted, not the head SHA the
    review job actually ran on."""
    candidates = sorted(
        (str(c.get("committedDate") or ""), i, str(c.get("oid") or ""))
        for i, c in enumerate(commits)
        if str(c.get("committedDate") or "") and str(c.get("oid") or "")
        and str(c.get("committedDate") or "") <= when
    )
    return candidates[-1][2] if candidates else ""


def _review_commit_oid(reviews: Sequence[Mapping], comment: Mapping) -> str:
    """The `commit.oid` GitHub stamped on the `CHANGES_REQUESTED` review
    `pr_review.py` posts alongside ``comment`` — see module docstring. Picks
    the closest-in-time eligible review inside the match window; returns
    ``""`` when none qualifies (wrong login, edited, wrong state, outside the
    window, or no ``commit.oid`` on the review at all)."""
    when = _parse_timestamp(str(comment.get("createdAt") or ""))
    if when is None:
        return ""
    best_oid, best_delta = "", None
    for review in reviews:
        author = review.get("author")
        login = str((author or {}).get("login") or "") if isinstance(author, Mapping) else ""
        if login != _BOT_AUTHOR_LOGIN or review.get("includesCreatedEdit"):
            continue
        if str(review.get("state") or "").upper() != "CHANGES_REQUESTED":
            continue
        submitted = _parse_timestamp(str(review.get("submittedAt") or ""))
        if submitted is None:
            continue
        delta = abs((submitted - when).total_seconds())
        if delta > _REVIEW_MATCH_WINDOW_SECONDS:
            continue
        commit = review.get("commit")
        oid = str((commit or {}).get("oid") or "") if isinstance(commit, Mapping) else ""
        if oid and (best_delta is None or delta < best_delta):
            best_oid, best_delta = oid, delta
    return best_oid


def _bind_commit(commits: Sequence[Mapping], reviews: Sequence[Mapping], comment: Mapping) -> str:
    """The commit ``comment`` is bound to — the authoritative review-based
    binding whenever review data was fetched at all (even if this particular
    comment matches no review in it — that is a real "unbindable", not a
    reason to guess), the `committedDate` approximation only when ``reviews``
    itself is empty (the fetch was not attempted or came back empty)."""
    if reviews:
        return _review_commit_oid(reviews, comment)
    return _commit_as_of(commits, str(comment.get("createdAt") or ""))


def verdicts_span_distinct_commits(
    commits: Sequence[Mapping], head_sha: str,
    previous_comment: Mapping, current_comment: Mapping,
    *, reviews: Sequence[Mapping] = (),
) -> bool:
    """Refuse to escalate on a stale, duplicate, or unbindable verdict pair —
    see "Commit binding" above. Fails OPEN (``False``, no escalation)
    whenever there is nothing to bind against — empty ``head_sha`` or both
    ``commits``/``reviews`` empty must never manufacture a halt.
    """
    if not head_sha or not (commits or reviews):
        return False
    current_bound = _bind_commit(commits, reviews, current_comment)
    previous_bound = _bind_commit(commits, reviews, previous_comment)
    if not current_bound or current_bound != head_sha:
        return False
    return bool(previous_bound) and previous_bound != current_bound
