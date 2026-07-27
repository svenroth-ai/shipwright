"""Name why an open pull request is not merging (iterate-2026-07-27-name-the-blocker).

The F11 delivery watch used to answer "why is this PR not merged yet?" with the
elapsed time. On PR #439 that meant three identical `{"status": "pending",
"timed_out": true}` reports over ~25 minutes while all ten check-runs were
successful and auto-merge was armed — the actual cause was one unresolved review
thread, which blocks auto-merge on its own. The watcher was already fetching
``mergeStateStatus`` and ignoring it.

Three sources, in increasing cost:

1. ``mergeStateStatus`` — already in the watcher's payload; a whole vocabulary of
   named states (conflicts, out-of-date, draft, blocked), not a yes/no flag.
2. **review threads** — one GraphQL query.
3. **required contexts** — one REST call to ``/repos/{o}/{r}/rules/branches/{b}``,
   which (unlike branch-protection reads) does not need admin.

Two rules govern the output, both learned from what the old behaviour got wrong:

* **Absence of evidence is not evidence.** A source that cannot be read lands in
  ``unknown`` with the reason, never in "nothing found". An unreadable rules
  endpoint must not read as "no required check is missing", a truncated thread
  page must not read as "no unresolved threads", and an unrecognised merge state
  must not read as "fine".
* **Report causes; assert blocking only where the host structurally cannot
  merge.** An unresolved review thread, an out-of-date branch, or a failing
  non-required check are named as causes without the claim, because whether they
  block depends on repository settings.

This module holds the ``gh`` shells; the pure judgement lives in
``_pr_blocker_causes`` and is re-exported here, so every import site sees one
surface.
"""

from __future__ import annotations

import json
import subprocess
from urllib.parse import quote

from ._pr_blocker_causes import (  # noqa: F401 — re-exported public surface
    MAX_REASON_CHARS,
    THREAD_PAGE_SIZE,
    _clip,
    _unknown,
    merge_state_blocks,
    merge_state_cause,
    required_check_causes,
    thread_causes,
)

_THREADS_QUERY = """
query($owner:String!,$name:String!,$number:Int!,$first:Int!){
  repository(owner:$owner,name:$name){
    pullRequest(number:$number){
      reviewThreads(first:$first){
        pageInfo{ hasNextPage }
        nodes{ isResolved isOutdated path line }
      }
    }
  }
}
"""


def summarize(
    *,
    merge_state: str,
    threads: dict | None,
    rules: object,
    rollup: list[dict] | None,
) -> dict:
    """Combine every source into one report.

    ``blocking`` stays the host's own verdict, never our inference — but it is
    now read from the whole ``mergeStateStatus`` vocabulary rather than from the
    single ``BLOCKED`` value.
    """
    causes: list[dict] = []
    unknown: list[dict] = []
    for fn_causes, fn_unknown in (
        merge_state_cause(merge_state),
        thread_causes(threads),
        required_check_causes(rules, rollup),
    ):
        causes.extend(fn_causes)
        unknown.extend(fn_unknown)
    return {
        "merge_state_status": _clip(merge_state or ""),
        "blocking": merge_state_blocks(merge_state),
        "causes": causes,
        "unknown": unknown,
    }


# ---------------------------------------------------------------------------
# gh shells
# ---------------------------------------------------------------------------


def _gh_json(args: list[str]) -> object | None:
    """Run a ``gh`` command and parse its JSON. ``None`` on any failure — the
    caller turns that into an explicit ``unknown`` source, never a clean answer."""
    try:
        proc = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0 or not (proc.stdout or "").strip():
        return None
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return None


def fetch_review_threads(owner: str, name: str, number: int) -> dict | None:
    """The PR's review threads, or ``None`` when unreadable."""
    payload = _gh_json([
        "gh", "api", "graphql",
        "-f", f"query={_THREADS_QUERY}",
        "-F", f"owner={owner}", "-F", f"name={name}",
        "-F", f"number={number}", "-F", f"first={THREAD_PAGE_SIZE}",
    ])
    if not isinstance(payload, dict):
        return None
    node = (((payload.get("data") or {}).get("repository") or {}).get("pullRequest") or {})
    threads = node.get("reviewThreads")
    return threads if isinstance(threads, dict) else None


def fetch_branch_rules(owner: str, name: str, branch: str) -> object | None:
    """The base branch's effective rules, or ``None`` when unreadable.

    The branch is URL-encoded: a ``release/1.2`` base would otherwise split the
    path and silently query a different (or nonexistent) branch.
    """
    if not branch:
        return None
    return _gh_json([
        "gh", "api", f"repos/{owner}/{name}/rules/branches/{quote(branch, safe='')}",
    ])


def probe(*, owner: str, name: str, number: int, branch: str,
          merge_state: str, rollup: list[dict] | None) -> dict:
    """Fetch both extra sources and summarise. Never raises."""
    try:
        threads = fetch_review_threads(owner, name, number)
        rules = fetch_branch_rules(owner, name, branch)
    except Exception as exc:  # noqa: BLE001 — a diagnostic must not sink the verdict
        return {
            "merge_state_status": _clip(merge_state or ""),
            "blocking": merge_state_blocks(merge_state),
            "causes": [],
            "unknown": [_unknown("probe", f"blocker probe failed: {type(exc).__name__}")],
        }
    return summarize(merge_state=merge_state, threads=threads, rules=rules, rollup=rollup)


__all__ = [
    "MAX_REASON_CHARS",
    "THREAD_PAGE_SIZE",
    "thread_causes",
    "required_check_causes",
    "summarize",
    "fetch_review_threads",
    "fetch_branch_rules",
    "probe",
]
