"""network_policy — decide whether GitHub enrichment may run, and record it.

Plan §14 D: the grader is **local-only by default** (private repos never leave
the machine). ``--allow-network`` is the master opt-in for all ``gh``/API/SARIF
enrichment. Even then, a **private** (or unverifiable) remote **auto-disables**
enrichment unless the user *also* passes ``--allow-network-private`` — so a
private repo can never silently leak just because the network switch was on.

The policy also accumulates a provenance log of *exactly which* enrichments left
the machine (:meth:`NetworkPolicy.record`), which the report stamps.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from gh_bridge import GhRunner, gh_json, owner_repo_from_remote


@dataclass
class NetworkPolicy:
    """The resolved enrichment decision + the provenance accumulator."""

    enabled: bool
    requested: bool
    owner: str | None
    repo: str | None
    visibility: str  # public | private | internal | unknown | local-only
    note: str
    enrichments: list[str] = field(default_factory=list)

    @property
    def slug(self) -> str:
        return f"{self.owner}/{self.repo}" if self.owner and self.repo else "?"

    def record(self, what: str) -> None:
        """Log an enrichment that actually ran (what left the machine)."""
        if what not in self.enrichments:
            self.enrichments.append(what)


def _local_only(note: str, *, requested: bool) -> NetworkPolicy:
    return NetworkPolicy(
        enabled=False, requested=requested, owner=None, repo=None,
        visibility="local-only", note=note)


def resolve_network_policy(
    *,
    allow_network: bool,
    allow_private: bool,
    remote_url: str,
    gh: GhRunner,
) -> NetworkPolicy:
    """Resolve the enrichment policy for a target (see module docstring)."""
    if not allow_network:
        return _local_only(
            "local-only (default) — pass --allow-network to enrich via GitHub",
            requested=False)

    parsed = owner_repo_from_remote(remote_url)
    if parsed is None:
        return _local_only(
            "network requested but no GitHub remote detected — local-only",
            requested=True)
    owner, repo = parsed

    # An authorized metadata probe (the user opted into the network with
    # --allow-network): reads only the repo's visibility, never code/findings.
    # A private result auto-disables the *signal* enrichments below.
    result, data = gh_json(gh, ["repo", "view", f"{owner}/{repo}", "--json", "visibility"])
    if result.error == "not_found":
        return _local_only(
            "network requested but the gh CLI is not available — local-only",
            requested=True)

    visibility = "unknown"
    if isinstance(data, dict) and isinstance(data.get("visibility"), str):
        visibility = data["visibility"].strip().lower()

    is_public = visibility == "public"
    if not is_public and not allow_private:
        reason = "private/internal" if visibility in ("private", "internal") else \
            "unverifiable"
        return NetworkPolicy(
            enabled=False, requested=True, owner=owner, repo=repo,
            visibility=visibility,
            note=(f"{reason} remote ({owner}/{repo}) — enrichment auto-disabled; "
                  "re-run with --allow-network-private to override"))

    return NetworkPolicy(
        enabled=True, requested=True, owner=owner, repo=repo,
        visibility=visibility,
        note=f"network enrichment enabled for {owner}/{repo} ({visibility})")
