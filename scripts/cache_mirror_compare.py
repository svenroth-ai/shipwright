#!/usr/bin/env python3
"""Drift check for the cross-plugin mirror tree, ``cache/plugins/<name>/``.

Split out of ``cache_tree_compare.py`` rather than folded in: that module
already backs the repo-vs-cache comparison for the ``plugins`` and ``shared``
trees, and the mirror's comparison rests on a genuinely different basis (see
below), not a variant of that one. A third leaf keeps each contract legible
on its own, the same reason ``cache_file_hash.py`` was split out before it.

**Own basis and verdict semantics (P2.29 / ADR-120).** The mirror's repair
source is not the repo and not ``installed_plugins.json`` — it is the
plugin's OWN newest cached version dir, exactly what
``ensure_shared_cache._heal_plugins`` treats as authoritative (the healer
never consults the manifest; mirroring the ``plugins`` tree's
``installed_plugins``-preferring rule here would hold the mirror to a
standard the healer was never built to satisfy). So this tree's ``basis`` is
always the literal string ``"cache"`` — never ``"git"`` and never a
``"walk (<why not git>)"`` fallback — because neither side was ever a git
tree: the source is itself a prior sync's cache-side copy. Folding mirror
records into ``cache_sync_report``'s git-fallback basis notes would misreport
an always-expected provenance as a degraded one, so callers must keep them
out of those notes.

The healer and this checker answer different questions and neither retires
the other: the healer detects ABSENCE with a file-set diff (``_delivered`` in
``ensure_shared_cache.py``) — no hashing at all, so a repo checkout's line
endings can never enter into it — while this checker detects STALENESS with
CRLF-normalized content hashes (:func:`cache_tree_compare.walk_tracked_files`).
Both sides here are already cache-side filesystem copies (the mirror is
``shutil.copytree``d from the version dir, never checked out from git), so
unlike the plugins/shared comparison there is no git-vs-clone line-ending
seam to bridge — the same hash function is reused for the drift-detection
contract, not because a mismatch is expected.
"""

from __future__ import annotations

import sys
from pathlib import Path

if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.append(str(Path(__file__).resolve().parent))

from cache_tree_compare import (  # noqa: E402
    latest_cache_version_dir,
    walk_tracked_files,
)


def _no_source() -> dict:
    """A fresh no-source record. A factory, not a module constant — see
    ``check_plugin_cache_sync._shared_na``'s same rule: a shared ``sample``
    list would be one ``.append()`` away from leaking between records."""
    return {"state": "no_source", "basis": "cache", "tracked_count": 0,
            "diff_count": 0, "missing_in_cache_count": 0, "cache_only_count": 0,
            "unhashable_count": 0, "sample": []}


def compare_mirror_tree(source_dir: Path | None, mirror_dir: Path) -> dict:
    """Compare one plugin's mirror against its own repair source.

    ``source_dir`` is the plugin's newest cached version dir (see
    :func:`compare_all_mirrors`), not the repo and not the
    ``installed_plugins``-resolved dir the ``plugins`` tree compares against.

    Returns a record shaped like :func:`cache_tree_compare.compare_tree`'s,
    but drawn from a distinct ``state`` vocabulary: ``no_source`` (the plugin
    has no cached version at all — already a finding on that plugin's
    ``plugins`` record, so it is NOT this tree's own drift), ``not_mirrored``
    (a source exists but the mirror dir does not, or is empty), ``drift``,
    ``ok``. A zero source is never read as agreement, matching
    :func:`cache_tree_compare.compare_tree`'s rule at its own entrance: an
    empty or unreadable source cannot certify the mirror ``ok`` over nothing.
    """
    if source_dir is None or not source_dir.is_dir():
        return _no_source()
    source_hashes = walk_tracked_files(source_dir)
    if not source_hashes:
        return _no_source()
    mirror_hashes = walk_tracked_files(mirror_dir) if mirror_dir is not None else {}
    if not mirror_hashes:
        return {"state": "not_mirrored", "basis": "cache",
                "tracked_count": len(source_hashes), "diff_count": len(source_hashes),
                "missing_in_cache_count": len(source_hashes), "cache_only_count": 0,
                "unhashable_count": 0, "sample": sorted(source_hashes)[:5]}
    diffs = [rel for rel in source_hashes if mirror_hashes.get(rel) != source_hashes[rel]]
    missing = [rel for rel in source_hashes if rel not in mirror_hashes]
    # Counted, not drift — same rule as compare_tree's cache_only_count: a
    # mirror file the source no longer has is an unpropagated deletion, not
    # this plugin's own staleness.
    cache_only = [rel for rel in mirror_hashes if rel not in source_hashes]
    return {
        "state": "drift" if diffs else "ok",
        "basis": "cache",
        "tracked_count": len(source_hashes),
        "diff_count": len(diffs),
        "missing_in_cache_count": len(missing),
        "cache_only_count": len(cache_only),
        "unhashable_count": 0,
        "sample": sorted(diffs)[:5],
    }


def compare_all_mirrors(plugin_names: list[str], cache_root: Path) -> list[dict]:
    """One :func:`compare_mirror_tree` record per name, each tagged ``plugin``.

    The source for ``<name>`` is ``latest_cache_version_dir(cache_root/<name>)``
    — the highest-SemVer cached version, matching
    ``ensure_shared_cache._plugin_mirrors`` exactly (both sort with the same
    SemVer key; pinned equal by ``test_ensure_shared_cache_ssot_pins.py``).
    Deliberately NOT ``resolve_version_dir``'s ``installed_plugins.json``
    preference: the healer this check audits never reads that manifest, so a
    stray higher version dir left over from an aborted sync (P2.06) is
    exactly what the healer would mirror from, and this check has to judge
    the mirror by the same rule the healer used to write it.
    """
    mirror_root = cache_root / "plugins"
    records = []
    for name in plugin_names:
        source_dir, _reason = latest_cache_version_dir(cache_root / name)
        record = compare_mirror_tree(source_dir, mirror_root / name)
        record["plugin"] = name
        records.append(record)
    return records
