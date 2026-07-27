"""Name why an open pull request is not merging (iterate-2026-07-27-name-the-blocker).

The F11 delivery watch used to answer "why is this PR not merged yet?" with the
elapsed time. On PR #439 that meant three identical `{"status": "pending",
"timed_out": true}` reports over ~25 minutes while all ten check-runs were
successful and auto-merge was armed — the actual cause was one unresolved review
thread, which blocks auto-merge on its own. The watcher was already fetching
``mergeStateStatus`` and ignoring it.

Three sources, in increasing cost:

1. ``mergeStateStatus`` — already in the watcher's payload. ``BLOCKED`` is the
   host's own statement that something is stopping the merge.
2. **review threads** — one GraphQL query.
3. **required contexts** — one REST call to ``/repos/{o}/{r}/rules/branches/{b}``,
   which (unlike branch-protection reads) does not need admin.

Two rules govern the output, both learned from what the old behaviour got wrong:

* **Absence of evidence is not evidence.** A source that cannot be read lands in
  ``unknown`` with the reason, never in "nothing found". An unreadable rules
  endpoint must not read as "no required check is missing", and a truncated
  thread page must not read as "no unresolved threads".
* **Report causes; assert blocking only when the host does.** An unresolved
  thread only blocks where the repository requires conversation resolution, so
  causes are named as candidates and ``blocking`` is asserted only on
  ``mergeStateStatus == "BLOCKED"``.

Pure summarisation lives here and is unit-tested; :func:`probe` is the thin
``gh`` shell.
"""

from __future__ import annotations

import json
import subprocess
from urllib.parse import quote

#: Host-supplied strings are diagnostics, not a channel for unbounded text.
MAX_REASON_CHARS = 300

#: How many review threads one query asks for. Beyond this the page is reported
#: as truncated rather than paginated — an unbounded walk on a pathological PR is
#: a worse failure than an explicit "there may be more".
THREAD_PAGE_SIZE = 100

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


def _clip(value: object) -> str:
    return str(value)[:MAX_REASON_CHARS]


def _unknown(source: str, reason: str) -> dict:
    return {"source": source, "reason": _clip(reason)}


# ---------------------------------------------------------------------------
# Pure summarisation
# ---------------------------------------------------------------------------


def thread_causes(threads: dict | None) -> tuple[list[dict], list[dict]]:
    """``(causes, unknown)`` for the review-thread source.

    ``threads`` is the ``reviewThreads`` object (``nodes`` + ``pageInfo``), or
    ``None`` when the query could not be read.
    """
    if not isinstance(threads, dict):
        return [], [_unknown("review_threads", "review threads could not be read")]

    nodes = threads.get("nodes") or []
    unresolved = [n for n in nodes if isinstance(n, dict) and n.get("isResolved") is False]

    causes: list[dict] = []
    if unresolved:
        causes.append({
            "kind": "unresolved_review_threads",
            "count": len(unresolved),
            "detail": [
                {"path": _clip(n.get("path") or "?"), "line": n.get("line")}
                for n in unresolved[:5]
            ],
        })

    unknown: list[dict] = []
    if (threads.get("pageInfo") or {}).get("hasNextPage"):
        # Reported whether or not we already found one: the count is a floor,
        # not a total, and a caller must not read "0 found" as "none exist".
        unknown.append(_unknown(
            "review_threads",
            f"more than {THREAD_PAGE_SIZE} threads — the page is truncated, so "
            "the unresolved count is a lower bound",
        ))
    return causes, unknown


def _required_contexts(rules: object) -> list[str] | None:
    """Required status-check contexts, ``[]`` when the branch requires none, or
    ``None`` when the rules could not be read.

    An **empty** list is ``None``, not ``[]``. The endpoint reports *rulesets*;
    a repository using classic branch protection has required checks that it
    cannot see and answers ``[]`` — indistinguishable from "no rules apply".
    Found by probing the live API against a branch with no ruleset. Reading that
    as "nothing is required" is precisely the false-clean this module exists to
    prevent, so an empty answer is an unknown. A NON-empty rule list with no
    ``required_status_checks`` entry is a real answer: rulesets are in force and
    none of them require a status check.
    """
    if not isinstance(rules, list) or not rules:
        return None
    # EVERY matching ruleset contributes. A branch can match several, so stopping
    # at the first ``required_status_checks`` rule would leave a check required by
    # a later ruleset unnamed when it never reports (external code review).
    contexts: list[str] = []
    seen: set[str] = set()
    for rule in rules:
        if not isinstance(rule, dict) or rule.get("type") != "required_status_checks":
            continue
        for entry in (rule.get("parameters") or {}).get("required_status_checks") or []:
            if isinstance(entry, dict) and entry.get("context"):
                context = str(entry["context"])
                if context not in seen:
                    seen.add(context)
                    contexts.append(context)
    return contexts  # [] is a definite answer: rulesets apply, none require a check


def _reported(rollup: list[dict] | None) -> dict[str, str]:
    """context/name → rollup status (``COMPLETED`` for a legacy StatusContext)."""
    seen: dict[str, str] = {}
    for entry in rollup or []:
        if not isinstance(entry, dict):
            continue
        if entry.get("__typename") == "StatusContext":
            seen[str(entry.get("context", ""))] = "COMPLETED"
        else:
            seen[str(entry.get("name", ""))] = str(entry.get("status") or "")
    return seen


def required_check_causes(
    rules: object, rollup: list[dict] | None
) -> tuple[list[dict], list[dict]]:
    """``(causes, unknown)`` for the required-status-check source."""
    required = _required_contexts(rules)
    if required is None:
        return [], [_unknown(
            "required_checks",
            "branch rules could not be read (token scope, classic branch "
            "protection, or a fork) — required checks are NOT known to be complete",
        )]

    reported = _reported(rollup)
    absent = [c for c in required if c not in reported]
    running = [c for c in required if reported.get(c) not in ("", "COMPLETED") and c in reported]

    causes: list[dict] = []
    if absent:
        causes.append({"kind": "required_check_never_reported", "checks": sorted(absent)})
    if running:
        causes.append({"kind": "required_check_still_running", "checks": sorted(running)})
    return causes, []


def summarize(
    *,
    merge_state: str,
    threads: dict | None,
    rules: object,
    rollup: list[dict] | None,
) -> dict:
    """Combine every source into one report.

    ``blocking`` is the host's own verdict (``mergeStateStatus == "BLOCKED"``),
    not our inference — ``causes`` are named candidates regardless.
    """
    causes: list[dict] = []
    unknown: list[dict] = []
    if (merge_state or "").strip().upper() in ("", "UNKNOWN"):
        # The host has not computed mergeability. Without this the report would
        # read as a confident "no blocker found" while the host's own verdict —
        # the most authoritative source here — is simply unavailable.
        unknown.append(_unknown(
            "merge_state_status",
            "the code host has not reported a merge state for this PR yet",
        ))
    for fn_causes, fn_unknown in (thread_causes(threads), required_check_causes(rules, rollup)):
        causes.extend(fn_causes)
        unknown.extend(fn_unknown)
    return {
        "merge_state_status": _clip(merge_state or ""),
        "blocking": (merge_state or "").upper() == "BLOCKED",
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
            "blocking": (merge_state or "").upper() == "BLOCKED",
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
