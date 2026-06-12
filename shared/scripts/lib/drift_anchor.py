"""Repo-relative dedup-anchor + project-guard helpers for the drift detector.

Extracted from ``check_drift.py`` (WP5 / 2026-06-10 deep audit, F7+F8): the
content-drift dedup key must be **repo-relative** so a drift recorded from the
main tree and the same drift seen later in a worktree collapse to ONE key, and
``_emit_drift_to_triage`` must no-op in a non-Shipwright tree. Keeping these here
also lets ``artifact_sync`` (the sibling ``source="drift"`` producer) reuse the
exact same canonicalization if it ever needs it.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

# Fallback only — the canonical strip is bloat_baseline.strip_worktree_prefix.
_WORKTREE_PREFIX_FALLBACK = re.compile(r"^\.worktrees/[^/]+/")


def is_shipwright_project(project_root) -> bool:
    """True iff ``project_root`` looks Shipwright-managed (F7 guard).

    Delegates to the canonical shared predicate; a minimal marker fallback keeps
    the guard from failing open into a foreign tree if the import is unavailable.
    """
    try:
        root = Path(project_root)
    except (TypeError, ValueError):
        return False
    try:
        scripts_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir)
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)
        from lib.project_root import _is_shipwright_project as _shared_marker  # noqa: PLC0415

        return bool(_shared_marker(root))
    except (ImportError, ValueError):
        return (root / "shipwright_run_config.json").exists()


def _strip_worktree_prefix(rel: str) -> str:
    """Strip a leading ``.worktrees/<slug>/`` (F8) — reuse the shared bloat
    helper; local-regex fallback when it can't be imported."""
    try:
        scripts_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir)
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)
        from lib.bloat_baseline import strip_worktree_prefix  # noqa: PLC0415

        return strip_worktree_prefix(rel)
    except (ImportError, ValueError):
        return _WORKTREE_PREFIX_FALLBACK.sub("", rel.replace("\\", "/"), count=1)


def canonical_anchor(anchor: str, project_root) -> str:
    """Canonicalize a content-finding path into a stable, **repo-relative** key.

    Folds Windows drive-letter case (Bug 1) AND strips the absolute tree prefix
    (F8) so a drift recorded from the main tree and the same drift seen later in
    a worktree share one dedup key (else the worktree session machine-dismisses
    the still-present drift). Best-effort: ``relative_to`` outside the root and
    exotic-path errors fall back to the normalised full/case-folded path.
    """
    try:
        root = Path(project_root).resolve()
        # An already-relative anchor must NOT be realpath'd (that joins it
        # against the process cwd, not project_root) — keep it, POSIX-normalised.
        if Path(anchor).is_absolute():
            resolved = Path(os.path.realpath(anchor))
            try:
                rel = resolved.relative_to(root).as_posix()
            except ValueError:
                rel = resolved.as_posix()  # outside root → strip prefix below
        else:
            rel = anchor.replace("\\", "/")
        return os.path.normcase(_strip_worktree_prefix(rel))
    except (OSError, ValueError):  # defensive only
        return os.path.normcase(str(anchor).replace("\\", "/"))


def content_anchor(finding: str, project_root) -> str:
    """Extract + canonicalize the stable path anchor of a content finding.

    Every content finding is shaped ``<path>: <human description>``; the path
    before the first ``': '`` is the anchor. Canonicalized **repo-relative** to
    ``project_root`` (F8) so the append loop and the resolve pass — possibly in
    different trees — agree on the exact dedup key.
    """
    raw = finding.split(": ", 1)[0].strip() or "CLAUDE.md"
    return canonical_anchor(raw, project_root)
