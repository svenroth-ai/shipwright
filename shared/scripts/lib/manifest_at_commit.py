"""Read a JSON manifest at an EXACT git commit via ``git show`` — never the
working-tree copy (P3.4c anchor promotion,
``.shipwright/planning/iterate/iterate-2026-09-10-p34c-promotion-anchor-guard.md``).

The one place both ``promote_required_layers._read_committed_manifest``
(pinned to ``HEAD``) and the anchor-evidence path (pinned to whatever verified
ancestor ``ci_verified_anchor.resolve_verified_anchor`` names) get this
TOCTOU-free primitive from — one commit-pinned read, reused verbatim rather
than re-implemented at each call site (the same discipline
``promote_required_layers.py``'s own docstring already states for its HEAD
read).
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

DEFAULT_MANIFEST_RELPATH = ".shipwright/compliance/test-traceability.json"

_GIT_TIMEOUT_SECONDS = 15

#: Same shape as `ci_provenance._COMMIT_RE` (external code review, low):
#: `sha` reaches `git show f"{sha}:{relpath}"` with no injection guard
#: otherwise. Today's only callers pass `resolve_head_sha`'s own output or
#: `ci_verified_anchor`'s validated candidates, so this is not exploitable
#: now -- validated anyway, matching the sibling predicate's convention.
_COMMIT_RE = re.compile(r"[0-9a-f]{40}")


class ManifestReadError(Exception):
    """A commit could not be resolved, or a manifest could not be read at
    that exact commit via ``git show``."""


def resolve_head_sha(project_root: Path) -> str:
    """The exact commit ``HEAD`` currently names, resolved once via
    ``git rev-parse``."""
    try:
        rev = subprocess.run(  # nosec B603,B607 - fixed argv, shell=False
            ["git", "-C", str(project_root), "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=_GIT_TIMEOUT_SECONDS,
            encoding="utf-8", errors="replace", check=False, shell=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ManifestReadError(f"could not run 'git rev-parse HEAD': {exc}") from exc
    if rev.returncode != 0:
        raise ManifestReadError(f"'git rev-parse HEAD' failed: {rev.stderr.strip()}")
    sha = rev.stdout.strip()
    if not sha:
        raise ManifestReadError("'git rev-parse HEAD' returned an empty SHA")
    return sha


def read_manifest_at_commit(
    project_root: Path, sha: str, *, relpath: str = DEFAULT_MANIFEST_RELPATH,
) -> dict:
    """The parsed JSON manifest at ``relpath`` as it existed at the exact
    commit ``sha`` — via ``git show <sha>:<relpath>``, never the on-disk
    working-tree copy (that file can differ from any given commit, and a
    caller evaluating evidence FOR a commit must never silently substitute
    a different one)."""
    if not (isinstance(sha, str) and _COMMIT_RE.fullmatch(sha.lower())):
        raise ManifestReadError(f"sha {sha!r} is not a 40 char hex SHA")
    try:
        show = subprocess.run(  # nosec B603,B607 - fixed argv, shell=False
            ["git", "-C", str(project_root), "show", f"{sha}:{relpath}"],
            capture_output=True, text=True, timeout=_GIT_TIMEOUT_SECONDS,
            encoding="utf-8", errors="replace", check=False, shell=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ManifestReadError(f"could not run 'git show {sha}:...': {exc}") from exc
    if show.returncode != 0:
        raise ManifestReadError(f"could not read {relpath!r} at {sha}: {show.stderr.strip()}")
    try:
        manifest = json.loads(show.stdout)
    except ValueError as exc:
        raise ManifestReadError(f"manifest at {sha} is not valid JSON: {exc}") from exc
    if not isinstance(manifest, dict):
        raise ManifestReadError(f"manifest at {sha} is not a JSON object")
    return manifest


__all__ = [
    "DEFAULT_MANIFEST_RELPATH",
    "ManifestReadError",
    "resolve_head_sha",
    "read_manifest_at_commit",
]
