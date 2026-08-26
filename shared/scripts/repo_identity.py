"""Normalize a git ``origin`` remote to a GitHub ``owner/repo`` identity.

One small shared helper so the release-notes link-host allowlist and every
``gh`` call that needs ``--repo`` agree on the same identity, instead of each
re-deriving it from ``git remote get-url origin`` (SSH vs HTTPS vs a trailing
``.git`` are all valid forms a contributor's git config can produce).

**Why this file sits at ``shared/scripts/`` top level and not under ``lib/``:**
ADR-045, same placement as ``changelog_sections.py`` (a direct sibling — read
that file's docstring for the full rationale). Every plugin ships its own
``scripts/lib`` package, so a shared helper placed under ``lib/`` risks a
future consumer importing it as ``lib.repo_identity`` and binding
``sys.modules['lib']`` to whichever plugin's ``lib`` package won the race;
this helper is consumed by both ``shared/scripts/tools/*`` and a plugin's own
``scripts/checks/``, which is exactly the shape that collision needs. It has
no intra-package imports (only ``re``/``subprocess``/``pathlib``), so every
consumer loads it as a private top-level ``repo_identity`` module instead.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

# git@github.com:owner/repo.git   (SCP-style SSH)
# ssh://git@github.com/owner/repo.git   (SSH URI form)
# https://github.com/owner/repo(.git)?
_SSH_SCP_RE = re.compile(r"^git@github\.com:(?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?$")
_SSH_URI_RE = re.compile(
    r"^ssh://git@github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?/?$"
)
_HTTPS_RE = re.compile(
    r"^https://github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?/?$"
)


def normalize_github_origin(url: str) -> str | None:
    """Return ``owner/repo`` for a github.com origin URL, else ``None``.

    Non-GitHub hosts (GHES, GitLab, ...) return ``None`` — this repo's own
    conventions are GitHub-only (see ``feedback_github_oss_only_no_ghas``),
    and a caller that gets ``None`` should treat identity as unresolvable
    rather than guess.
    """
    url = url.strip()
    for pattern in (_SSH_SCP_RE, _SSH_URI_RE, _HTTPS_RE):
        match = pattern.match(url)
        if match:
            return f"{match.group('owner')}/{match.group('repo')}"
    return None


def resolve_repo_identity(project_root: Path) -> str | None:
    """Run ``git remote get-url origin`` in ``project_root`` and normalize it.

    Returns ``None`` on any git failure or a non-GitHub / unparseable origin.
    """
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=str(project_root),
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    return normalize_github_origin(result.stdout.strip())
