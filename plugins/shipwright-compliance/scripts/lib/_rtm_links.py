"""RTM link / anchor / ordering helpers (usability iterate 2026-06-30).

Extracted from :mod:`rtm_generator` so that grandfathered module stays under its
anti-ratchet ceiling. Pure stdlib + the shared :mod:`event_display` leaf — it
never imports ``rtm_generator``, so no cycle.

These render the navigable affordances the Requirements Traceability Matrix
gained for usability:

* :func:`fr_anchor_id` — the in-document anchor id stamped on each Requirements
  Coverage row so the Verification Timeline FRs can link back to it.
* :func:`timeline_order` — newest-first (descending) Verification Timeline order.
* :func:`resolve_repo_url` / :func:`commit_cell` — link a commit SHA to its
  GitHub diff when the project's ``origin`` remote is resolvable.
* :func:`last_tested_cell` — link the ``(iter)`` token in Requirements Coverage
  to the event's full row in the Verification Timeline.
* :func:`link_frs` — link each declared FR in the Verification Timeline to its
  coverage-row anchor.
"""

from __future__ import annotations

import re
import subprocess
from datetime import datetime, timezone

from scripts.lib.event_display import event_anchor

# Events whose timestamp won't parse sort below every real date (descending).
_MIN_TS = datetime.min.replace(tzinfo=timezone.utc)


def fr_anchor_id(fr_id: str) -> str:
    """In-document anchor id for an FR's Requirements Coverage row.

    The ``rtm-`` prefix keeps it distinct from the spec.md heading anchor
    (``fr-0101``) that the Requirement cell links OUT to, so the two never
    collide inside the rendered matrix.
    """
    return "rtm-" + fr_id.lower().replace(".", "")


def timeline_order(events):
    """Verification Timeline order: newest first, stable.

    Sorts by parsed timestamp descending; an event whose timestamp won't parse
    sorts to the end in its original relative position (never crashes the
    render).
    """
    def _key(we):
        try:
            dt = datetime.fromisoformat((we.timestamp or "").replace("Z", "+00:00"))
        except (ValueError, AttributeError, TypeError):
            dt = None
        return (1, dt) if dt is not None else (0, _MIN_TS)

    return sorted(events, key=_key, reverse=True)


def resolve_repo_url(project_root) -> str:
    """Best-effort HTTPS base of the project's ``origin`` remote, else ``""``.

    Normalizes the SSH form ``git@host:owner/repo(.git)`` to
    ``https://host/owner/repo`` and strips a trailing ``.git``. Fail-soft: no
    git, no remote, or an odd URL all yield ``""`` so commit links simply don't
    render (matches the rest of the RTM's never-crash contract).
    """
    try:
        out = subprocess.run(
            ["git", "-C", str(project_root), "remote", "get-url", "origin"],
            capture_output=True, text=True, timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    if out.returncode != 0:
        return ""
    url = (out.stdout or "").strip()
    if not url:
        return ""
    m = re.match(r"^git@([^:]+):(.+?)(?:\.git)?/?$", url)
    if m:
        return f"https://{m.group(1)}/{m.group(2)}"
    return re.sub(r"\.git/?$", "", url).rstrip("/")


def commit_cell(commit: str, repo_url: str) -> str:
    """Short SHA, linked to its GitHub diff when a repo url is known."""
    short = commit[:7] if commit else "—"
    if repo_url and commit:
        return f"[{short}]({repo_url}/commit/{commit})"
    return short


def last_tested_cell(latest) -> str:
    """``<date> (iter|build)`` with the ``iter`` token linked to the event's
    Verification Timeline anchor (same document); build / non-canonical id stays
    plain text."""
    last_ts = latest.timestamp[:10]
    if latest.source == "iterate":
        frag = event_anchor(latest.id)
        tag = f"[iter]({frag})" if frag else "iter"
    else:
        tag = "build"
    return f"{last_ts} ({tag})"


def link_frs(affected_frs, known_fr_ids) -> str:
    """Verification Timeline FRs cell: declared FRs link to their coverage-row
    anchor, FRs absent from the requirements set stay plain text. Mirrors the
    prior ``+N`` overflow after the first three."""
    parts = [
        f"[{fr}](#{fr_anchor_id(fr)})" if fr in known_fr_ids else fr
        for fr in affected_frs[:3]
    ]
    cell = ", ".join(parts)
    if len(affected_frs) > 3:
        cell += f" +{len(affected_frs) - 3}"
    return cell


__all__ = [
    "commit_cell",
    "fr_anchor_id",
    "last_tested_cell",
    "link_frs",
    "resolve_repo_url",
    "timeline_order",
]
