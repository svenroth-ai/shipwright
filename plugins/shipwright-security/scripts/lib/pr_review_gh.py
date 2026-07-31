"""The `gh`-CLI boundary for the Tier-3 PR reviewer.

Thin subprocess wrappers only: fetch the PR's diff, post the review comment,
post the review state, and — for clearing this reviewer's superseded verdicts —
read the PR's reviews, read its head SHA, dismiss one review. Split out of
`pr_review.py` so the tool script keeps to the source-size guideline and the
subprocess surface — the one place where attacker-controlled bytes enter the
process — is its own reviewable module. The rules about WHICH review may be
dismissed are policy and live in `pr_review_dismiss`; this module only makes
the calls.

See `pr_review_diff_filter._split_sections` for why the fetch reads bytes.
"""

from __future__ import annotations

import json
import subprocess

__all__ = ["dismiss_pr_review", "fetch_pr_diff", "fetch_pr_head_sha",
           "list_pr_reviews", "post_pr_comment", "post_pr_review_state"]


def fetch_pr_diff(pr_number: int, repo: str) -> str:
    """Fetch the unified diff for a PR via the `gh` CLI.

    Read as BYTES and decode without newline translation. `text=True` would run
    CPython's universal-newline pass, which rewrites a lone CR to LF **before any
    parser sees it** — and git ends a diff line at LF only. A PR whose own
    content carries a CR could therefore manufacture a line break, and with it a
    counterfeit `diff --git` header at column 0, splitting one real file section
    into two. Everything downstream — the generated-artifact filter, the size
    cap, the file lists shown to the model and to humans — trusts that boundary.
    """
    proc = subprocess.run(
        ["gh", "pr", "diff", str(pr_number), "--repo", repo],
        capture_output=True,
        timeout=120,
    )
    if proc.returncode != 0:
        err = proc.stderr.decode("utf-8", "replace").strip()
        raise RuntimeError(f"`gh pr diff` failed ({proc.returncode}): {err}")
    return proc.stdout.decode("utf-8", "replace")


# `encoding=` rather than `text=True` on every call that carries a body: the
# rendered comment always contains non-ASCII (the decision badges), and
# `text=True` encodes with the locale's preferred encoding. On a runner whose
# LC_CTYPE is not UTF-8 that raises, the caller swallows it best-effort, and the
# maintainer is left with a red required check and no comment explaining it.
_TEXT = {"encoding": "utf-8", "errors": "replace"}


def post_pr_comment(pr_number: int, repo: str, body: str) -> None:
    """Post the review comment to the PR via `gh pr comment` (stdin body)."""
    proc = subprocess.run(
        ["gh", "pr", "comment", str(pr_number), "--repo", repo, "--body-file", "-"],
        input=body,
        capture_output=True,
        timeout=60,
        **_TEXT,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"`gh pr comment` failed ({proc.returncode}): {proc.stderr.strip()}")


def post_pr_review_state(pr_number: int, repo: str, decision: str, summary: str) -> None:
    """Post a review state (best-effort): block -> request-changes, else -> comment.

    Deliberately never `--approve` (a bot approving its own org's PR is noise and
    can fail). The merge gate is the workflow job's exit code, not this state.

    Best-effort means the gate does not flip on a failure — not that a failure
    goes unrecorded. `gh pr review` fails on a rate limit, a revoked token, or
    "can not review your own pull request"; raising lets the caller log it.
    """
    norm = (decision or "").strip().lower()
    flag = "--request-changes" if norm == "block" else "--comment"
    body = summary or "Automated Tier-3 review."
    proc = subprocess.run(
        ["gh", "pr", "review", str(pr_number), "--repo", repo, flag, "--body", body],
        capture_output=True,
        timeout=60,
        **_TEXT,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"`gh pr review` failed ({proc.returncode}): {proc.stderr.strip()}")


def _decode_pages(raw: str) -> list[dict]:
    """Read `gh api --paginate` output, whichever shape it arrives in.

    gh 2.92 merges the pages into ONE array (measured); older releases emit one
    array per page, concatenated. `raw_decode` in a loop reads both.

    `--jq` is not the shorter route here, despite `fetch_pr_head_sha` using it
    below: gh applies the filter PER PAGE, so `--jq '.[]'` returns NDJSON that
    still has to be reassembled line by line. Same amount of parsing, one more
    thing that can be wrong.

    A page that is not an array RAISES. `gh` can exit 0 and hand back an error
    object (`{"message": "Not Found"}`); reading that as "no reviews" is not
    failing safe, it is reporting a PR we could not read as a clean one — and
    the caller would then say "this run's own review is not visible yet", which
    sends the reader looking in the wrong place entirely.
    """
    decoder = json.JSONDecoder()
    items: list[dict] = []
    index, end = 0, len(raw)
    while index < end:
        while index < end and raw[index].isspace():
            index += 1
        if index >= end:
            break
        page, index = decoder.raw_decode(raw, index)
        if not isinstance(page, list):
            raise ValueError(
                f"expected a JSON array of reviews, got {type(page).__name__}")
        items.extend(entry for entry in page if isinstance(entry, dict))
    return items


def list_pr_reviews(pr_number: int, repo: str) -> list[dict]:
    """Every review on the PR: `id`, `state`, `commit_id`, `body`, `user`."""
    proc = subprocess.run(
        ["gh", "api", "--paginate", f"repos/{repo}/pulls/{pr_number}/reviews?per_page=100"],
        capture_output=True,
        timeout=60,
        **_TEXT,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"`gh api …/reviews` failed ({proc.returncode}): {proc.stderr.strip()}")
    return _decode_pages(proc.stdout)


def fetch_pr_head_sha(pr_number: int, repo: str) -> str:
    """The PR's CURRENT head. Read fresh: a verdict about a commit that is no
    longer the head has no standing to retract one that might be."""
    proc = subprocess.run(
        ["gh", "api", f"repos/{repo}/pulls/{pr_number}", "--jq", ".head.sha"],
        capture_output=True,
        timeout=60,
        **_TEXT,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"`gh api …/pulls` failed ({proc.returncode}): {proc.stderr.strip()}")
    return proc.stdout.strip()


def dismiss_pr_review(pr_number: int, repo: str, review_id: int, message: str) -> None:
    """Dismiss one review.

    `message` is REQUIRED by the endpoint — probed live: omitting it answers
    `422 "message" wasn't supplied` before any other validation, so a wrapper
    without it would fail every single time. `event=DISMISS` is accepted but is
    not part of the documented request, and the same probe shows the call
    behaves identically without it, so it is not sent.
    """
    proc = subprocess.run(
        ["gh", "api", "--method", "PUT",
         f"repos/{repo}/pulls/{pr_number}/reviews/{review_id}/dismissals",
         "-f", f"message={message}"],
        capture_output=True,
        timeout=60,
        **_TEXT,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"`gh api …/dismissals` failed ({proc.returncode}): {proc.stderr.strip()}")
