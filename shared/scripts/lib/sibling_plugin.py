"""Locate a sibling Shipwright plugin from a file inside the calling plugin.

Two layouts exist and a hard-coded ``this_plugin.parent / "<name>"`` only holds
in the first:

* **Repo** — ``<root>/plugins/<plugin>/…``: the sibling is
  ``<root>/plugins/<name>``.
* **Plugin cache** — ``<cache>/shipwright/<plugin>/<version>/…``: the sibling is
  one of ``<cache>/shipwright/<name>/<version>``. Several versions can be
  installed side by side and the plugins version independently of each other,
  so the *newest installed* one is used, not "the same version as the caller".

Stdlib only, no ``lib`` import: callers load this file by path (ADR-045), so it
must not depend on any package namespace.
"""

from __future__ import annotations

import re
from pathlib import Path

_PLUGIN_MARKER = Path(".claude-plugin") / "plugin.json"
# The Claude Code cache manager flags a superseded version with this marker and
# reaps it later (possibly only in part); such a directory is not "installed".
_ORPHAN_MARKER = ".orphaned_at"
_SEMVER_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)(.*)$")


def _own_plugin_root(anchor: Path) -> Path | None:
    """The nearest ancestor of ``anchor`` that is a plugin root, else None."""
    for parent in anchor.resolve().parents:
        if (parent / _PLUGIN_MARKER).is_file():
            return parent
    return None


def _version_key(path: Path) -> tuple:
    """Sort key: ``MAJOR.MINOR.PATCH`` numerically, a release above its pre-release,
    names that are not SemVer-shaped (a commit sha, a stray folder) below all of them.

    Same rule as ``scripts/cache_tree_compare.version_key`` (kept as a copy: this
    file is stdlib-only and loaded by path, so it cannot import it).
    """
    m = _SEMVER_RE.match(path.name)
    if not m:
        return (-1, -1, -1, -1, path.name)
    suffix = m.group(4) or ""
    return (int(m.group(1)), int(m.group(2)), int(m.group(3)), 0 if suffix else 1, suffix)


def find_sibling_plugin(
    anchor: Path | str, name: str, require: str | None = None,
) -> Path | None:
    """Return the root of sibling plugin ``name``, or None when not installed.

    ``anchor`` is any file inside the calling plugin (usually ``__file__``).
    ``require`` is a path relative to the sibling's root that must exist (for
    example ``scripts/tools/update_compliance.py``): a version directory without
    it — a partly reaped install — is skipped, so the newest *usable* version wins.
    """
    own = _own_plugin_root(Path(anchor))
    if own is None:
        return None

    def usable(root: Path) -> bool:
        return (
            (root / _PLUGIN_MARKER).is_file()
            and not (root / _ORPHAN_MARKER).exists()
            and (require is None or (root / require).exists())
        )

    repo_candidate = own.parent / name
    if usable(repo_candidate):
        return repo_candidate

    # Cache layout: own = <cache>/shipwright/<plugin>/<version>.
    versions_dir = own.parent.parent / name
    if not versions_dir.is_dir():
        return None
    installed = [d for d in versions_dir.iterdir() if usable(d)]
    return max(installed, key=_version_key) if installed else None
