#!/usr/bin/env python3
"""SessionStart hook: self-heal the plugin cache for marketplace installs.

Shipwright plugins reach shared code AND sibling-plugin code through relative
paths two levels above the plugin root:

- ``${CLAUDE_PLUGIN_ROOT}/../../shared/...``               — every hook;
- ``${CLAUDE_PLUGIN_ROOT}/../../plugins/shipwright-X/...`` — cross-plugin libs
  (e.g. ``phase_session_start`` imports the shipwright-run ``phase_task_lifecycle``).

So a marketplace install needs a sibling ``shared/`` AND a sibling ``plugins/``
at ``.../plugins/cache/shipwright/{shared,plugins}``. But a plain
``claude plugin install`` copies ONLY each plugin's own source into the cache;
neither ``shared/`` nor the ``plugins/`` cross-link tree is a plugin, so neither
is delivered — only the dev script ``scripts/update-marketplace.sh`` creates them.
On a fresh install every ``../../shared/*`` hook 404s (``track_tool_calls.py``
"can't find its own path") and cross-plugin imports degrade to their None
fallback (``phase_session_start`` crashed on one before its guard landed).

This hook self-heals both, stdlib-only + fail-open + idempotent:

- ``shared/``  — mirrored from the marketplace full-clone
  (``~/.claude/plugins/marketplaces/<name>/shared``, which a marketplace install
  DOES carry);
- ``plugins/`` — mirrored from the already-installed versioned plugin dirs
  (``cache/<name>/shipwright-X/<version>``), so ``../../plugins/shipwright-X``
  resolves. Needs no clone.

Any error exits 0 (a session is never blocked); a sentinel + per-plugin existence
check make it a no-op once healed, and always in the ``--plugin-dir`` dev model
(where both dirs are the real repo). This file is the CANONICAL source vendored
byte-identically into every hook-bearing plugin's ``scripts/hooks/`` (a
plugin-local file is the only reliable marketplace delivery); drift is gated by
``shared/tests/test_ensure_shared_cache_vendored.py``. Edit here, then re-vendor.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

# Sentinels that exist inside a healthy shared/ resp. plugins/ tree.
_SHARED_SENTINEL = ("scripts", "lib", "project_root.py")
_PLUGINS_SENTINEL = ("shipwright-run", "scripts", "lib", "phase_task_lifecycle.py")
_IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc", ".venv", ".pytest_cache", ".git")


def _shared_healthy(shared_dir: Path) -> bool:
    return shared_dir.is_dir() and shared_dir.joinpath(*_SHARED_SENTINEL).is_file()


def _plugins_healthy(plugins_dir: Path) -> bool:
    return plugins_dir.is_dir() and plugins_dir.joinpath(*_PLUGINS_SENTINEL).is_file()


def _find_marketplace_shared(cache_marketplace_root: Path) -> Path | None:
    """Locate the marketplace full-clone's shared/ dir, or None.

    ``cache_marketplace_root`` is ``.../.claude/plugins/cache/<name>``; the clone
    lives at ``.../.claude/plugins/marketplaces/<name>``. Try the same-name path
    first, then scan ``marketplaces/*/shared`` for any clone carrying the sentinel.
    """
    plugins_root = cache_marketplace_root.parent.parent  # cache/<name> -> cache -> plugins
    marketplaces = plugins_root / "marketplaces"
    if not marketplaces.is_dir():
        return None
    same = marketplaces / cache_marketplace_root.name / "shared"
    if _shared_healthy(same):
        return same
    for entry in sorted(marketplaces.iterdir()):
        candidate = entry / "shared"
        if _shared_healthy(candidate):
            return candidate
    return None


def _heal_plugins(cache_marketplace_root: Path, plugins_target: Path) -> bool:
    """Mirror each installed plugin (``cache/<name>/shipwright-X/<version>``) into
    ``cache/<name>/plugins/shipwright-X`` so ``../../plugins/shipwright-X`` refs
    resolve. Per-plugin idempotent; needs no marketplace clone. The
    ``shipwright-`` name filter keeps this safe if ever reached in the dev model
    (a repo root has no ``shipwright-*`` top-level dirs)."""
    healed = False
    for plugin_dir in sorted(cache_marketplace_root.iterdir()):
        if not plugin_dir.is_dir() or not plugin_dir.name.startswith("shipwright-"):
            continue
        dst = plugins_target / plugin_dir.name
        if dst.exists():
            continue  # already mirrored
        versions = sorted((v for v in plugin_dir.iterdir() if v.is_dir()), key=lambda v: v.name)
        if not versions:
            continue
        shutil.copytree(versions[-1], dst, ignore=_IGNORE)  # newest installed version
        healed = True
    return healed


def main() -> int:
    # Hook protocol: consume stdin, never fail on it.
    try:
        json.load(sys.stdin)
    except Exception:
        pass

    try:
        plugin_root = Path(__file__).resolve().parents[2]  # scripts/hooks/<f> -> plugin root
        cache_root = plugin_root.parent.parent             # cache/<name> (or the repo, in dev)
        shared_target = cache_root / "shared"
        plugins_target = cache_root / "plugins"

        if _shared_healthy(shared_target) and _plugins_healthy(plugins_target):
            return 0  # fully present (dev repo, or already healed) — no-op

        healed: list[str] = []

        if not _shared_healthy(shared_target):
            source = _find_marketplace_shared(cache_root)
            if source is not None:
                shutil.copytree(source, shared_target, ignore=_IGNORE, dirs_exist_ok=True)
                healed.append("shared")

        if not _plugins_healthy(plugins_target) and _heal_plugins(cache_root, plugins_target):
            healed.append("plugins")

        if healed:
            print(f"shipwright: self-healed the plugin cache ({', '.join(healed)})", file=sys.stderr)
        if not _shared_healthy(shared_target):
            print(
                "shipwright: shared/ is missing from the plugin cache and no "
                "marketplace clone was found to self-heal from. Run "
                "`bash scripts/update-marketplace.sh` from the shipwright repo "
                "to restore it.",
                file=sys.stderr,
            )
    except Exception as exc:  # never block a session
        print(f"shipwright: ensure_shared_cache skipped ({exc!r})", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
