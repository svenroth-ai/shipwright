"""The host-touching half of the non-converging halt (trg-ac24ec5b, PR #690).

`lib.pr_review_convergence` is the pure predicate — no `gh`, no host, testable
on plain dicts. This module is the one call that fetches what it needs to ask
that predicate and turns a match into the escalated delivery verdict
`tools/deliver_pr.py` returns. Split out when `deliver_pr.py` crossed the
300-line source limit, the same reason `lib.pr_self_merge` and `lib.pr_delivery`
exist as their own modules.
"""

from __future__ import annotations

from pathlib import Path

from lib.automerge_readiness import POSTED_STATUS_CONTEXTS
from lib.pr_delivery import EXIT_NON_CONVERGING, delivery_result
from lib.pr_delivery_host import Host
from lib.pr_review_convergence import non_converging

__all__ = ["PR_REVIEW_CHECK_NAME", "describe_non_converging", "escalate_if_non_converging"]

#: The one check name this escalation ever looks at. Any other failing check —
#: the test suite, lint, a required workflow — takes the ordinary EXIT_CHECKS_FAILED
#: path unchanged; this module adds memory to nothing except this one gate
#: (scope guard 1: the gate itself stays stateless, this reads it from the
#: outside, after it has already failed twice). Read from `automerge_readiness`
#: (the one place that already canonicalises the posted-status-context name per
#: workflow, with its own drift test) rather than redefined here, so a rename of
#: `pr-review-run.yml`'s check does not silently stop this escalation from
#: firing (code-reviewer, Stage 2).
PR_REVIEW_CHECK_NAME = POSTED_STATUS_CONTEXTS["pr-review-run.yml"]


def escalate_if_non_converging(result: dict, *, pr_url: str, project_root: Path,
                               host: Host) -> dict:
    """Call unconditionally on every ladder result — a no-op on anything but a
    `checks_failed` verdict whose failing check is `PR Review`. Promotes to
    `non_converging` (exit 8) when the last two `PR Review` BLOCK comments on
    this PR also share a recurring (file, claim) finding.

    Fails OPEN to the unmodified `result`, never to a manufactured halt: any
    other status, a failing check that isn't `PR Review`, a `gh` read that
    comes back empty, or two verdicts that genuinely differ all leave the
    ladder's own verdict exactly as it was — this only ever REPLACES
    `checks_failed`/EXIT_CHECKS_FAILED with a stricter one, never invents a
    problem the ladder did not already report (scope guard 2: this may never
    make a review more lenient or block something that would otherwise pass —
    it only recognises when re-pushing is not the remedy).
    """
    if result.get("status") != "checks_failed":
        return result
    failed_checks = (result.get("watch") or {}).get("failed") or []
    if not any(str(c.get("name") or "") == PR_REVIEW_CHECK_NAME for c in failed_checks):
        return result
    payload = host.call_json(
        ["pr", "view", pr_url, "--json", "comments,commits,headRefOid,reviews"],
        cwd=project_root)
    comments = (payload or {}).get("comments") if isinstance(payload, dict) else None
    if not comments:
        return result
    commits = (payload or {}).get("commits") or []
    reviews = (payload or {}).get("reviews") or []
    head_sha = str((payload or {}).get("headRefOid") or "")
    match = non_converging(comments, commits=commits, head_sha=head_sha, reviews=reviews)
    if match is None:
        return result
    steps = [*result.get("steps", []),
            "non-converging: the last two `PR Review` BLOCK verdicts share a "
            "recurring finding — re-pushing is not the remedy"]
    return delivery_result(
        "non_converging", EXIT_NON_CONVERGING, steps,
        watch=result.get("watch"), checks_observed=result.get("checks_observed"),
        reason="two consecutive PR-review BLOCK verdicts carry the same blocking "
               "finding — the fix is not addressing it",
        previous_verdict=_verdict_excerpt(match["previous_comment"], match["previous_finding"]),
        current_verdict=_verdict_excerpt(match["current_comment"], match["current_finding"]),
    )


def _verdict_excerpt(comment: dict, finding: dict) -> dict:
    """One BLOCK verdict, reduced to what the operator needs to compare it
    against its neighbour: when it was posted, where to read it in full, and
    the specific blocking line the predicate matched on."""
    return {
        "posted_at": str(comment.get("createdAt") or ""),
        "url": str(comment.get("url") or ""),
        "blocking_finding": finding.get("raw", ""),
    }


def describe_non_converging(result: dict) -> str:
    """The operator-facing line: both verdicts, quoted side by side, and the
    one instruction that matters — re-running this changes nothing."""
    previous = result.get("previous_verdict") or {}
    current = result.get("current_verdict") or {}
    return (
        "NOT DELIVERED — NON-CONVERGING. Two consecutive PR-review BLOCKs carry "
        "the same blocking finding. STOP. Do not fix and re-push; hand back to "
        f"the operator.\nPrevious ({previous.get('posted_at', '?')}, "
        f"{previous.get('url', '?')}): {previous.get('blocking_finding', '?')}\n"
        f"Current ({current.get('posted_at', '?')}, {current.get('url', '?')}): "
        f"{current.get('blocking_finding', '?')}"
    )
