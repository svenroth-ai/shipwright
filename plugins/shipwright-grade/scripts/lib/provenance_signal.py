"""provenance_signal — change-traceability provenance, best-available (dim 3).

The Control-Grade *change traceability* dimension asks "is every change linked to
a reviewed unit of work". In an authoritative Shipwright grade that is the event
log's real commit/ADR/test provenance. For a COLD external repo the projector
falls back to git-log PR/issue references — but that signal **anti-correlates with
quality** (G6 root cause 3): a disciplined repo that squash-merges reviewed PRs
leaves plain, reference-free commit subjects, so it reads LOW while a repo that
pastes ``#123`` into every subject reads HIGH. flask (exemplary) scores 0.14 by
git-log, *below* request (deprecated) at 0.20.

The faithful signal is GitHub's own PR-association: how many recent
default-branch commits were introduced by a **merged, reviewed pull request**
(``associatedPullRequests``). This is exactly SLSA's / OpenSSF Scorecard's
code-review provenance, and squash-merge preserves it even when the commit
subject does not. It is a **network** tier; the git-log count stays the offline
fallback, so an offline grade still produces an honest (if conservative) number.

The signal is a *ratio* the projector maps onto ``events_with_provenance`` (it
scales the count so the engine's ``events_with_provenance / events_total``
dimension is unchanged in shape — only its input is more faithful).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from gh_bridge import GhRunner, default_branch, gh_json
from network_policy import NetworkPolicy

# Recent default-branch commits sampled for the PR-association ratio. Bounded so
# the query is one cheap call; the ratio is applied to the full event count.
_HISTORY_SAMPLE = 100
_PR_ASSOCIATION_QUERY = (
    "query($owner:String!,$repo:String!,$branch:String!){"
    "repository(owner:$owner,name:$repo){"
    "ref(qualifiedName:$branch){target{... on Commit{"
    "history(first:" + str(_HISTORY_SAMPLE) + "){nodes{"
    "associatedPullRequests(first:1){nodes{merged}"
    "}}}}}}}}"
)


@dataclass(frozen=True)
class ProvenanceSignal:
    """Change-traceability provenance. ``ratio`` is the [0,1] share of recent
    commits introduced by a merged PR; None when the network tier didn't resolve
    (the projector then keeps its git-log fallback count)."""

    measurable: bool
    ratio: float | None
    tier: str            # pr-association | git-log
    detail: str


def provenance_event_count(ratio: float, events_total: int) -> int:
    """Scale a [0, 1] PR-association ratio onto an ``events_with_provenance`` count.

    Round HALF-UP (not banker's ``round``, which sends an exact-half count DOWN):
    the resulting ``events_with_provenance / events_total`` must not dip below a
    measured ratio that meets the honesty gate's 0.5 collapse bar, or a repo at
    exactly 50% reviewed-PR provenance flips C->F on the count's parity. Clamp to
    ``[0, events_total]`` defensively so a malformed ratio can never feed the
    unchanged scorer an impossible count.
    """
    return max(0, min(events_total, int(ratio * events_total + 0.5)))


def _pr_association(gh: GhRunner, owner: str, repo: str) -> float | None:
    """Share of recent default-branch commits linked to a MERGED PR, or None."""
    branch = default_branch(gh, owner, repo)
    if not branch:
        return None
    result, data = gh_json(gh, [
        "api", "graphql", "-f", f"query={_PR_ASSOCIATION_QUERY}",
        "-f", f"owner={owner}", "-f", f"repo={repo}", "-f", f"branch={branch}"])
    if not result.ok or not isinstance(data, dict):
        return None
    try:
        nodes = data["data"]["repository"]["ref"]["target"]["history"]["nodes"]
    except (KeyError, TypeError):
        return None
    if not isinstance(nodes, list) or not nodes:
        return None
    linked = sum(
        1 for c in nodes
        if isinstance(c, dict) and any(
            (p or {}).get("merged")
            for p in ((c.get("associatedPullRequests") or {}).get("nodes") or [])))
    return linked / len(nodes)


def compute_provenance_signal(
    policy: NetworkPolicy,
    gh: GhRunner,
    *,
    assoc: Callable[[GhRunner, str, str], float | None] | None = None,
) -> ProvenanceSignal:
    """Network PR-association provenance; ``n/a`` (git-log fallback) otherwise."""
    assoc = assoc or _pr_association
    if policy.enabled and policy.owner and policy.repo:
        ratio = assoc(gh, policy.owner, policy.repo)
        if ratio is not None:
            policy.record(f"PR-association ({policy.owner}/{policy.repo})")
            return ProvenanceSignal(
                measurable=True, ratio=ratio, tier="pr-association",
                detail=(f"{round(ratio * 100)}% of recent commits introduced by a "
                        "reviewed, merged PR (SLSA code-review provenance)"))
    return ProvenanceSignal(
        measurable=False, ratio=None, tier="git-log",
        detail="git-log PR/issue references only (no network enrichment)")
