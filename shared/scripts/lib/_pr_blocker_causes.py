"""Why an open pull request is not merging — the pure judgement half.

Split out of ``pr_blockers`` in iterate-2026-07-27-merge-state-vocabulary to hold
the 300-line ceiling; ``pr_blockers`` keeps the ``gh`` shells and re-exports
everything here, so every existing import site is unchanged.

The rule this module exists to enforce: **absence of evidence is not evidence.**
Every source answers with named causes, or with an explicit ``unknown`` carrying
its reason — never with silence that a caller would read as "nothing is wrong".
"""

from __future__ import annotations

#: Host-supplied strings are diagnostics, not a channel for unbounded text.
MAX_REASON_CHARS = 300

#: How many review threads one query asks for. Beyond this the page is reported
#: as truncated rather than paginated — an unbounded walk on a pathological PR is
#: a worse failure than an explicit "there may be more".
THREAD_PAGE_SIZE = 100

def _clip(value: object) -> str:
    """Bound a host-supplied string AND strip control characters.

    These strings come from GitHub — branch names, file paths, merge states —
    and end up in an operator's terminal. A path may legally contain an escape
    sequence, so clipping the length is not enough on its own; defence in depth
    for every consumer, not just the one renderer.
    """
    text = str(value)[:MAX_REASON_CHARS]
    return "".join(ch if ch == " " or ch.isprintable() else "?" for ch in text)


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


#: GitHub's ``MergeStateStatus`` enum, as a CLOSED vocabulary: state → (detail,
#: does-it-block). ``None`` marks a state that is fine — nothing to report.
#:
#: This used to be read as a boolean ("is it BLOCKED?"), which dropped every
#: other actionable value on the floor. Found by running the shipped watcher on
#: a real stuck PR: all required checks green, no unresolved thread, and
#: ``DIRTY`` — the host stating the branch conflicts with its base — reported as
#: "no blocker found ... most likely still queued".
#:
#: ``blocking`` is claimed only where GitHub structurally cannot merge. BEHIND
#: depends on the repository's "require branches to be up to date" setting and
#: UNSTABLE is mergeable by definition, so both are NAMED without the claim —
#: the same posture as an unresolved review thread.
_MERGE_STATES: dict[str, tuple[str, bool] | None] = {
    "CLEAN": None,
    "HAS_HOOKS": None,
    "BLOCKED": ("the code host reports the merge as blocked (branch protection)", True),
    "DIRTY": ("the branch conflicts with its base and the merge commit cannot be created", True),
    "DRAFT": ("the pull request is still a draft", True),
    "BEHIND": ("the base branch has moved; this branch must be updated first", False),
    "UNSTABLE": ("a non-required check is failing (the merge itself is not blocked)", False),
}

#: States that mean "the host has not answered", as opposed to "the host says fine".
_MERGE_STATE_UNANSWERED = frozenset({"", "UNKNOWN"})


def merge_state_cause(merge_state: str | None) -> tuple[list[dict], list[dict]]:
    """``(causes, unknown)`` for the host's own merge verdict.

    An unrecognised value is ``unknown``, never silently fine: GitHub can add an
    enum member, and a state we cannot interpret is exactly the case where
    claiming "no blocker" would be a lie.
    """
    state = (merge_state or "").strip().upper()
    if state in _MERGE_STATE_UNANSWERED:
        return [], [_unknown(
            "merge_state_status",
            "the code host has not reported a merge state for this PR yet",
        )]
    if state not in _MERGE_STATES:
        return [], [_unknown(
            "merge_state_status",
            f"unrecognised merge state {state!r} — cannot tell whether it blocks",
        )]
    entry = _MERGE_STATES[state]
    if entry is None:
        return [], []
    detail, _blocks = entry
    return [{"kind": "merge_state", "state": state, "detail": detail}], []


def merge_state_blocks(merge_state: str | None) -> bool:
    """True only where GitHub structurally cannot merge."""
    entry = _MERGE_STATES.get((merge_state or "").strip().upper())
    return bool(entry and entry[1])



__all__ = [
    "MAX_REASON_CHARS",
    "THREAD_PAGE_SIZE",
    "thread_causes",
    "required_check_causes",
    "merge_state_cause",
    "merge_state_blocks",
]
