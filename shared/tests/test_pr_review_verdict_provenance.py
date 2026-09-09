"""Commit-binding provenance for the non-converging halt (trg-ac24ec5b, PR #690).

`test_pr_review_convergence.py` covers the sameness predicate end to end
through `non_converging`; this file is `lib.pr_review_verdict_provenance`'s
own — the two doubt-reviewer Stage-3 HIGH findings this unit's authoritative
commit binding exists to close:

* a forged BLOCK-shaped comment, authored by the real bot login and unedited
  (everything `is_authentic` alone checks), must still fail to bind when no
  sibling `CHANGES_REQUESTED` review exists near its timestamp — the
  structural fix for the login-only forgery gap (HIGH #1);
* the real PR #690 pair binds via `reviews[].commit.oid`, GitHub's own stamp,
  not a `committedDate` guess (HIGH #2) — and that binding survives even
  though #690's `commits[]` history no longer does (it was rebased in a
  later, unrelated session; the review data was not).
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))
sys.path.append(str(Path(__file__).resolve().parent))

from lib.pr_review_verdict_provenance import verdicts_span_distinct_commits  # noqa: E402

from _pr690_review_fixtures import (  # noqa: E402
    ROUND2_COMMIT_SHA,
    round1_comment,
    round2_comment,
    round_reviews,
)


def test_real_pr690_pair_binds_via_review_commit_oid_not_committed_date():
    """The primary path: no `commits[]` supplied at all — only `reviews`,
    which is what a real `gh pr view` payload always carries."""
    assert verdicts_span_distinct_commits(
        [], ROUND2_COMMIT_SHA, round1_comment(), round2_comment(),
        reviews=round_reviews(),
    ) is True


def test_forged_comment_with_no_sibling_review_does_not_bind():
    """`bloat-check.yml` posts PR comments under the SAME `github-actions`
    login as the real reviewer, built from file paths with no character
    restriction — a collaborator naming a file so its path contains both
    marker strings gets them echoed into a real, unedited, correctly-authored
    comment. `is_authentic` alone cannot see the difference; this can, because
    `bloat-check.yml` never posts a `CHANGES_REQUESTED` review, so the forged
    comment has nothing to correlate to."""
    # Real reviews exist (round1's/round2's own), but this pair is posted at
    # timestamps well outside either review's match window — simulating a
    # forged pair `bloat-check.yml` posted hours away from any real review.
    forged_previous = dict(round1_comment())
    forged_previous["createdAt"] = "2026-09-08T02:00:00Z"
    forged_current = dict(round2_comment())
    forged_current["createdAt"] = "2026-09-08T03:00:00Z"
    assert verdicts_span_distinct_commits(
        [], ROUND2_COMMIT_SHA, forged_previous, forged_current,
        reviews=round_reviews(),
    ) is False


def test_reviews_present_but_empty_match_does_not_fall_back_to_commits():
    """Once `reviews` was fetched at all, an unmatched comment must not fall
    back to the `commits[]` guess — that fallback exists only for when the
    fetch itself came back empty, not for "fetched, but this one didn't
    match" (the exact gap a forged comment would otherwise exploit)."""
    same_commit_commits = [{"oid": ROUND2_COMMIT_SHA, "committedDate": "2026-09-08T00:00:00Z"}]
    unmatched = dict(round1_comment())
    unmatched["createdAt"] = "2020-01-01T00:00:00Z"  # far outside any review's window
    assert verdicts_span_distinct_commits(
        same_commit_commits, ROUND2_COMMIT_SHA, unmatched, round2_comment(),
        reviews=round_reviews(),
    ) is False


def test_empty_reviews_falls_back_to_committed_date_binding():
    """`reviews=()` (the fetch itself came back empty, or an older caller
    that never passed it) must still work via the original approximation —
    this is a REGRESSION guard on the fallback path, not new behaviour."""
    commits = [
        {"oid": "aaa", "committedDate": "2026-09-08T08:00:00Z"},
        {"oid": ROUND2_COMMIT_SHA, "committedDate": "2026-09-08T08:45:00Z"},
    ]
    previous = dict(round1_comment())
    previous["createdAt"] = "2026-09-08T08:10:00Z"  # binds to "aaa"
    current = dict(round2_comment())
    current["createdAt"] = "2026-09-08T09:00:00Z"  # binds to ROUND2_COMMIT_SHA
    assert verdicts_span_distinct_commits(
        commits, ROUND2_COMMIT_SHA, previous, current, reviews=(),
    ) is True


def test_committed_date_ties_break_by_array_order_not_oid_text():
    """Two commits landing in the same second (a squash-merge push, or clock
    resolution) must resolve to whichever `gh pr view --json commits` listed
    LAST — array order is chronological; an oid's lexical value carries no
    ordering information at all (doubt-reviewer, Stage 3 LOW)."""
    tie = "2026-09-08T08:45:00Z"
    # "zzz" sorts after ROUND2_COMMIT_SHA lexically but is listed FIRST, i.e.
    # OLDER — a lexical tie-break would wrongly pick it as "most recent".
    commits = [
        {"oid": "prev", "committedDate": "2026-09-08T08:00:00Z"},
        {"oid": "zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz", "committedDate": tie},
        {"oid": ROUND2_COMMIT_SHA, "committedDate": tie},
    ]
    current = dict(round2_comment())
    current["createdAt"] = "2026-09-08T09:00:00Z"  # binds via tie-break, ROUND2 listed last
    previous = dict(round1_comment())
    previous["createdAt"] = "2026-09-08T08:05:00Z"  # binds unambiguously to "prev"
    assert verdicts_span_distinct_commits(
        commits, ROUND2_COMMIT_SHA, previous, current, reviews=(),
    ) is True
