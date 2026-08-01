#!/usr/bin/env python3
"""Detect drift between the local plugin cache and the repo HEAD.

Iterate C.3 (ADR-061) — closes the open gap from CLAUDE.md's "plugin-side fixes
silently never take effect" learning: changes under ``plugins/*`` and
``shared/scripts/`` aren't auto-synced to the runtime cache at
``~/.claude/plugins/cache/shipwright/`` unless ``scripts/update-marketplace.sh``
is run. Iterates 7-11 all had plugin-side fixes that landed in the dev repo but
never reached runtime because the sync step was skipped.

Two of the cache's trees are compared, and a green means both were read:

- ``cache/<plugin>/<version>/`` — the installed plugins;
- ``cache/shared/``            — reached as ``{plugin_root}/../../shared``, and
  the home of the F11 finalization verifier every iterate runs.

Only the first was compared until 2026-08-01, so ``--strict`` could print
"all 14 plugin(s) in sync" with the whole of ``shared/scripts/`` deleted from
the cache. That is not a hypothetical: a partial reap (see ``.orphaned_at``
below) leaves the SessionStart self-heal hook's sentinel intact, so nothing
repairs it and F11 dies with ``ModuleNotFoundError``.

A third tree, ``cache/plugins/<plugin>/`` (the cross-plugin mirror behind
``{plugin_root}/../../plugins/shipwright-X``), is not compared here. It once
could not be: ``ensure_shared_cache`` judged that whole tree from a single
sentinel file, so a gate on top of it would have inherited the weakness. Since
iterate-2026-08-01-cache-heal-per-plugin the healer compares each tree's FILE
SET against its repair source, so joining the mirror here is now plain follow-up
work (``trg-5005bf57``) rather than a blocked one. The healer is not a
substitute: it detects ABSENCE, this check detects STALENESS.

``.orphaned_at`` files are written by the Claude Code cache manager into
directories it does not recognise as an installed plugin. Nothing in this repo
writes them; this check is their only reader. They are NOT a reap prediction —
measured 2026-08-01, all 8 top-level subdirs of a fully intact cached
``shared/`` carried one, re-written by a recurring sweep after each re-sync
removed them, because "not referenced by ``installed_plugins.json``" is
permanently true of ``shared/`` by construction. So they never set exit 1, and
the human advisory prints only alongside drift, where it explains WHY a tree
lost files. ``orphan_markers`` is in the ``--json`` payload unconditionally.

Drift surfaces as a WARN line on stderr; exit code is 0 except when ``--strict``
is passed (which exits 1 on any drift).

CI-safe: when ``~/.claude/`` doesn't exist (typical in CI runners), the script
no-ops with status ``cache_root_absent``.

Usage:
    uv run scripts/check_plugin_cache_sync.py [--strict] [--json]
    uv run scripts/check_plugin_cache_sync.py --cache-root <path> --repo-root <path>
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Reach the sibling module when imported by something that hasn't already put
# this dir on the path. APPEND, never insert(0): prepending would let these
# top-level module names win resolution inside any host process that imports
# us (the ADR-045 lib-collision failure mode, one directory over). Nothing
# here needs precedence.
_HERE = str(Path(__file__).resolve().parent)
if _HERE not in sys.path:
    sys.path.append(_HERE)

from cache_sync_report import (  # noqa: E402
    UNGATED as _UNGATED,
)
from cache_sync_report import (  # noqa: E402
    print_drift,
    print_ok,
    print_orphan_advisory,
)
from cache_tree_compare import (  # noqa: E402
    compare_tree,
    find_orphan_markers,
    latest_cache_version_dir,
)

_SHARED_DIR = "shared"


def _default_cache_root() -> Path:
    return Path.home() / ".claude" / "plugins" / "cache" / "shipwright"


def _default_repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _repo_plugin_dirs(plugins_dir: Path) -> list[Path] | None:
    """Repo plugin dirs, or ``None`` when the dir exists but can't be listed.

    ``None`` is NOT the empty list. Swallowing the OSError into ``[]`` made an
    unreadable ``plugins/`` print "ok — 0 plugin(s) … in sync" and exit 0; the
    pre-extraction code had no guard there and at least crashed loudly.
    """
    try:
        entries = sorted(plugins_dir.iterdir())
    except OSError:
        return None
    return [p for p in entries if p.is_dir() and p.name.startswith("shipwright-")]


def _shared_na() -> dict:
    """A fresh not-applicable record.

    A factory, not a module constant: a shared ``sample`` list would be one
    ``.append()`` away from leaking between results.
    """
    return {"state": "n/a", "basis": "n/a", "tracked_count": 0, "diff_count": 0,
            "missing_in_cache_count": 0, "cache_only_count": 0,
            "unhashable_count": 0, "sample": []}


def _result(status: str, cache_root: Path, **extra) -> dict:
    """Every return carries the full documented shape, on every status.

    The early-return statuses used to omit ``shared`` / ``orphan_markers``
    entirely, so a ``--json`` consumer got a payload the docstring denied.
    """
    return {"status": status, "drifted_count": 0, "plugins": [],
            "shared": _shared_na(), "orphan_markers": [],
            # A machine consumer must be able to tell WHICH trees a green
            # covers. `status: ok` alone is the pre-fix guarantee, because it
            # reads the same whether shared/ was compared or skipped as n/a.
            "verified": [], "ungated": [_UNGATED],
            "cache_root": str(cache_root), **extra}


def check_sync(*, repo_root: Path, cache_root: Path) -> dict:
    """Compare the cache trees this check owns against the repo.

    Returns a structured dict, with every key present on every status:
    - ``status``: ``ok`` | ``drift`` | ``cache_root_absent`` | ``no_repo_plugins``
      | ``plugins_unreadable``
    - ``plugins``: per-plugin records for ``cache/<plugin>/<version>/``
    - ``shared``: one record for ``cache/shared/`` (``state: "n/a"`` when the
      repo has no ``shared/`` — only the monorepo does, and its absence
      elsewhere is not a finding)
    - ``orphan_markers``: cache-relative dirs flagged for reaping (advisory)
    - ``verified``: which trees this verdict actually covers
    - ``ungated``: which it knowingly does not
    - ``drifted_count``: total drifted records across both compared trees

    Best-effort: no exception leaks out; OSError on cache traversal is treated
    as "not in cache".
    """
    plugins_dir = repo_root / "plugins"
    if not cache_root.is_dir():
        return _result("cache_root_absent", cache_root)
    if not plugins_dir.is_dir():
        return _result("no_repo_plugins", cache_root)

    repo_plugins = _repo_plugin_dirs(plugins_dir)
    if repo_plugins is None:
        return _result("plugins_unreadable", cache_root, drifted_count=1)

    drifted = 0
    plugins: list[dict] = []
    verified: list[str] = []
    # Only the trees compared below are scanned for reap markers, so the
    # advisory can never fill up with un-gated paths (see find_orphan_markers).
    scopes: list[Path] = []

    for plugin_dir in repo_plugins:
        plugin_cache = cache_root / plugin_dir.name
        version_dir, reason = latest_cache_version_dir(plugin_cache)
        if reason == "unreadable":
            # Do NOT hand this to compare_tree: it would report every repo file
            # as missing from the cache, a number it never measured.
            record = {"state": "unreadable", "basis": "n/a", "tracked_count": 0,
                      "diff_count": 0, "missing_in_cache_count": 0,
                      "cache_only_count": 0, "unhashable_count": 0,
                      "sample": [], "detail": f"cannot list {plugin_cache}"}
        else:
            record = compare_tree(plugin_dir, version_dir)
            if version_dir is None:
                record["detail"] = f"no cached version under {plugin_cache}"
            else:
                record["cache_version"] = version_dir.name
                # Scope the marker scan at the PLUGIN base, not the version
                # dir: the cache manager writes `.orphaned_at` one level above
                # too, and that marker — "the whole plugin is up for reaping" —
                # is the most severe one there is.
                scopes.append(plugin_cache)
        record["plugin"] = plugin_dir.name
        plugins.append(record)
        if record["state"] != "ok":
            drifted += 1
    # Only when EVERY plugin was actually compared. A record refused as
    # `unreadable` never reached compare_tree, and folding it in here would
    # reinstate — one level down — the overclaim `verified` exists to prevent.
    if plugins and all(p["state"] != "unreadable" for p in plugins):
        verified.append("plugins")

    repo_shared = repo_root / _SHARED_DIR
    if repo_shared.is_dir():
        cache_shared = cache_root / _SHARED_DIR
        shared = compare_tree(repo_shared, cache_shared)
        scopes.append(cache_shared)
        # Same guard as the plugins one above. `not_in_cache` still counts as
        # verified — the repo side WAS established and the cache side was
        # determined to be absent, which is a finding. Only `unreadable` means
        # no basis was established at all, and claiming to cover a tree whose
        # own record says that is the overclaim `verified` exists to prevent.
        if shared["state"] != "unreadable":
            verified.append("shared")
        if shared["state"] != "ok":
            drifted += 1
    else:
        shared = _shared_na()

    return _result(
        "drift" if drifted else "ok", cache_root,
        drifted_count=drifted, plugins=plugins, shared=shared,
        verified=verified, orphan_markers=find_orphan_markers(cache_root, scopes),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Plugin-cache vs repo sync check")
    parser.add_argument("--repo-root", default=str(_default_repo_root()))
    parser.add_argument("--cache-root", default=str(_default_cache_root()))
    parser.add_argument("--strict", action="store_true",
                        help="Exit 1 on any drift (default: fail-soft WARN, exit 0).")
    parser.add_argument("--json", action="store_true",
                        help="Emit structured JSON on stdout instead of human prose.")
    args = parser.parse_args(argv)

    result = check_sync(repo_root=Path(args.repo_root), cache_root=Path(args.cache_root))
    status = result["status"]

    if args.json:
        print(json.dumps(result, indent=2))
    elif status == "cache_root_absent":
        print(f"plugin-cache-sync: skip — {result['cache_root']} doesn't exist (CI?)")
    elif status == "no_repo_plugins":
        # Reviewer-flagged code-review-M2: AC-4 says this state must be a
        # no-op-friendly return, not a drift warning. The repo has no
        # `plugins/` dir at all → nothing to compare against.
        print("plugin-cache-sync: skip — no plugins/ dir in repo")
    elif status == "plugins_unreadable":
        print(f"plugin-cache-sync: ERROR — {Path(args.repo_root) / 'plugins'} "
              f"exists but cannot be listed; nothing was compared.", file=sys.stderr)
    elif status == "ok":
        print_ok(result)
    elif status == "drift":
        print_drift(result)
        # Only here: on a green these markers are permanently present and
        # would be pure noise (see _print_orphan_advisory).
        print_orphan_advisory(result.get("orphan_markers", []))
    else:
        # Unknown status — print a diagnostic but don't fail.
        print(f"plugin-cache-sync: unknown status {status!r}", file=sys.stderr)

    return 1 if (args.strict and status in ("drift", "plugins_unreadable")) else 0


if __name__ == "__main__":
    sys.exit(main())
