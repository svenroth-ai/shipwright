#!/usr/bin/env python3
"""Tree-comparison primitives for the plugin-cache drift check.

Extracted from ``check_plugin_cache_sync.py`` when that check grew from one
compared tree to two (the versioned plugin dirs and ``shared/``).

The two sides are established differently and deliberately: the repo side asks
git (:func:`repo_tracked_files`), the cache side walks (:func:`walk_tracked_files`),
because only one of them is a git tree. Everything here is best-effort — this
backs a detective check that must never crash a session, so filesystem errors
degrade to "no hash" rather than propagating.
"""

from __future__ import annotations

import re
import subprocess
import sys
from collections.abc import Iterable
from pathlib import Path, PurePosixPath

# APPEND, never insert: this directory holds top-level module names, and winning
# resolution for the whole process is the ADR-045 collision class one dir over.
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.append(str(Path(__file__).resolve().parent))

# Re-exported: file_hash lived here until this module hit its 300-line ceiling.
from cache_file_hash import file_hash  # noqa: E402,F401

# The CACHE side's definition of "the tree": everything except these. A
# seven-suffix ALLOWLIST here left 44 of 1005 cached shared/ files invisible
# until 2026-08-01 (docs/guide.md has the account); an allowlist only works if
# it names every extension anyone will ever add.
# Matched per PATH COMPONENT, so every name must be one that can never be a
# real directory. ``build``/``dist``/``venv`` were here and are gone —
# ``plugins/shipwright-build/skills/build/`` is 29 tracked files including its
# SKILL.md, and a bare ``build`` dropped all 29 from both sides.
# ``node_modules`` (a ~13k-file speed-up) and ``.in_use`` (the cache manager's
# volatile per-PID refcounts, which made ``cache_only_count`` non-deterministic)
# stay because nothing tracked lives under either. Since the repo side asks git
# and this side does not, that invariant is load-bearing:
# ``test_skip_dirs_hide_nothing_git_tracks`` pins it.
SKIP_DIRS = {"__pycache__", ".git", ".venv", ".pytest_cache", "node_modules",
             ".in_use"}
SKIP_SUFFIXES = (".pyc", ".pyo")

#: Files git TRACKS that `update-marketplace.sh` never copies — a third category beside
#: SKIP_DIRS (tracked nowhere) and real drift. Filtered REPO-side only, so a stale
#: cached copy still surfaces as `cache_only`. Keep entries NARROW: a filtered name can
#: never be a diff, so an over-broad one downgrades content drift to an advisory count.
#: Rationale + the pin against the shell: test_marketplace_excludes_python_version.py.
NOT_DISTRIBUTED = frozenset({".python-version"})

#: Written by the Claude Code cache manager into a directory it considers
#: unreferenced, ahead of reaping it. Nothing in this repo writes it;
#: :func:`find_orphan_markers` is the only reader.
ORPHAN_MARKER = ".orphaned_at"


def walk_tracked_files(root: Path) -> dict[str, str]:
    """Return ``{relative_posix_path: sha256}`` for files under ``root``.

    The CACHE side's basis. Skips :data:`SKIP_DIRS`, :data:`SKIP_SUFFIXES` and
    :data:`ORPHAN_MARKER` — cache-only, so it would read as a file the repo is
    missing. Defensive: an OSError mid-traversal short-circuits this tree's
    dict rather than propagating (Gemini + OpenAI "isolate filesystem errors").
    """
    out: dict[str, str] = {}
    if not root.is_dir():
        return out
    try:
        entries = list(root.rglob("*"))
    except OSError:
        return out
    for entry in entries:
        try:
            if not entry.is_file():
                continue
            rel_parts = entry.relative_to(root).parts
        except OSError:
            continue
        if any(part in SKIP_DIRS for part in rel_parts):
            continue
        if entry.suffix.lower() in SKIP_SUFFIXES or entry.name == ORPHAN_MARKER:
            continue
        digest = file_hash(entry)
        if digest is None:
            continue
        out[entry.relative_to(root).as_posix()] = digest
    return out


def _has_any_file(root: Path) -> bool:
    """Cheap "is there anything here at all" probe; short-circuits."""
    try:
        return any(p.is_file() for p in root.rglob("*"))
    except OSError:
        return False  # unreadable reads as empty: nothing to contradict git


def _git_listing(root: Path) -> tuple[list[str] | None, str]:
    """``git ls-files`` under ``root``, or ``None`` plus why we fell back.

    An empty listing over a NON-empty directory is a refusal, not agreement:
    git exits 0 printing nothing when the path is in a repo that tracks nothing
    there, and read as success that yields ``ok`` over zero files.

    The reason rides in the basis string rather than collapsing to ``walk``,
    because "no repo here" (legitimate) and "git refused" (``safe.directory``
    on a UNC path or a container uid) are different facts, and the second
    silently restores the phantom drift the git basis exists to remove.
    """
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), "ls-files", "-z"],
            capture_output=True, timeout=120, check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return None, f"walk (git unavailable: {type(exc).__name__})"
    if proc.returncode != 0:
        lines = proc.stderr.decode("utf-8", "replace").strip().splitlines()
        detail = lines[0][:120] if lines else f"exit {proc.returncode}"
        return None, f"walk (git failed: {detail})"
    paths = [p for p in proc.stdout.decode("utf-8", "replace").split("\0") if p]
    if not paths and _has_any_file(root):
        return None, "walk (git tracks nothing under this path)"
    return paths, "git"


def repo_tracked_files(root: Path) -> tuple[dict[str, str], str, int]:
    """Hash what GIT tracks under ``root``; fall back to the walk without it.

    Returns ``(hashes, basis, unhashable_count)``. ``basis`` is ``git`` or a
    ``walk (...)`` string naming why git was not used. ``unhashable_count`` is
    how many files git listed that could not be hashed — see below.

    Git is authoritative here because the cache is copied from a clone holding
    exactly the tracked files, so "what git tracks" is "what can ever reach the
    cache" (docs/guide.md has the two measured failures that forced it).

    Git also says how many files SHOULD be here, so a listed file we cannot
    hash is COUNTED, not dropped: shrinking ``tracked_count`` to match would
    let a partial checkout, an AV lock, a cloud placeholder or a submodule
    gitlink self-consistently report ``ok`` over a partial basis.

    :data:`NOT_DISTRIBUTED` names ARE dropped: an unhashable file is of UNKNOWN state
    (dropping it would hide a partial basis), a not-distributed one is KNOWN
    not-comparable — a definitional narrowing, like :data:`SKIP_DIRS`.
    """
    listed, basis = _git_listing(root)
    if listed is None:
        walked = {rel: d for rel, d in walk_tracked_files(root).items()
                  if PurePosixPath(rel).name not in NOT_DISTRIBUTED}
        return walked, basis, 0
    # Dropped before hashing and before tracked_count: a file the sync never copies is
    # not something the cache is missing, and counting it makes `ok` unreachable.
    pre_filter = len(listed)
    listed = [rel for rel in listed if PurePosixPath(rel).name not in NOT_DISTRIBUTED]
    if pre_filter and not listed:
        # A zero must never read as agreement (as _git_listing's own guard): an entry
        # broad enough to empty a listing would yield tracked_count 0 and state `ok`.
        return {}, f"{basis} (NOT_DISTRIBUTED filtered every tracked file)", pre_filter
    out: dict[str, str] = {}
    for rel in listed:
        digest = file_hash(root / rel)
        if digest is not None:
            out[rel] = digest
    return out, basis, len(listed) - len(out)


def compare_tree(repo_dir: Path, cache_dir: Path | None) -> dict:
    """Compare one repo directory against its cache equivalent.

    Returns ``{state, tracked_count, diff_count, missing_in_cache_count,
    sample}`` where ``state`` is ``ok`` | ``drift`` | ``not_in_cache``.

    Drift = ANY repo file whose cache equivalent is missing or hashes
    differently. ``sample`` carries five offenders in sorted order, and the
    counts let an operator tell trivial from significant drift (OpenAI-L12).

    The repo side is read BEFORE the cache side is found absent, so a
    ``not_in_cache`` record reports how much is missing rather than a bare
    "gone" — a full hash on a cache-less machine, accepted because this is a
    manual dev command, not a hook.
    """
    repo_hashes, basis, unhashable = repo_tracked_files(repo_dir)
    if unhashable and not repo_hashes:
        # The same rule as _git_listing's, at the second place a zero can
        # enter: nothing HASHED over a non-empty listing is a refusal, not
        # agreement. Offline cloud placeholders, a disconnected mount, an AV
        # quarantine or an all-gitlink tree would otherwise read as `ok` over
        # zero files with --strict exit 0.
        return {"state": "unreadable", "basis": basis, "tracked_count": 0,
                "diff_count": 0, "missing_in_cache_count": 0,
                "cache_only_count": 0, "unhashable_count": unhashable,
                "sample": [], "detail": f"none of {unhashable} tracked file(s) readable"}
    if cache_dir is None or not cache_dir.is_dir():
        return {
            "state": "not_in_cache",
            "basis": basis,
            "tracked_count": len(repo_hashes),
            "diff_count": len(repo_hashes),
            "missing_in_cache_count": len(repo_hashes),
            "cache_only_count": 0,
            "unhashable_count": unhashable,
            "sample": sorted(repo_hashes)[:5],
        }
    cache_hashes = walk_tracked_files(cache_dir)
    diffs = [rel for rel in repo_hashes if cache_hashes.get(rel) != repo_hashes[rel]]
    missing = [rel for rel in repo_hashes if rel not in cache_hashes]
    # Counted, not drift: a file the cache still has after the repo dropped it
    # is a DELETION the syncer has not propagated. It stays importable at
    # runtime (shared/scripts is put on sys.path), so silence would be wrong —
    # but a legitimately cache-only artifact must not fail the gate either.
    cache_only = [rel for rel in cache_hashes if rel not in repo_hashes]
    return {
        "state": "drift" if diffs else "ok",
        "basis": basis,
        "tracked_count": len(repo_hashes),
        "diff_count": len(diffs),
        "missing_in_cache_count": len(missing),
        "cache_only_count": len(cache_only),
        "unhashable_count": unhashable,
        "sample": sorted(diffs)[:5],
    }


def find_orphan_markers(cache_root: Path, scopes: Iterable[Path]) -> list[str]:
    """Cache-relative dirs the cache manager has flagged for reaping.

    Never drift. The marker means "not recognised as an installed plugin",
    permanently true of ``shared/`` — all 8 of its top-level subdirs carried
    one on a fully intact cache — so it is no reap prediction, and the caller
    prints it only to explain a drift (``print_orphan_advisory``).

    Scanned per ``scopes``, the trees this check gates, not the whole cache
    root: 14 of the live cache's 22 markers sat under the un-gated mirror and,
    sorted, crowded ``shared/scripts`` out of a truncated advisory entirely.
    """
    out: set[str] = set()
    for scope in scopes:
        if not scope.is_dir():
            continue
        try:
            for marker in scope.rglob(ORPHAN_MARKER):
                out.add(marker.parent.relative_to(cache_root).as_posix())
        except (OSError, ValueError):
            continue
    return sorted(out)


_SEMVER_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)(.*)$")


def version_key(name: str) -> tuple:
    """Numeric-tuple sort key for SemVer-shaped dir names.

    Reviewer-flagged Gemini-S1 + OpenAI-M2: pure lexical sort puts ``0.10.0``
    before ``0.2.0`` (since ``'1' < '2'``). Parse the leading
    ``MAJOR.MINOR.PATCH`` triplet as ints; any pre-release / suffix stays a
    string tail. Non-SemVer names sort before any real version.

    OpenAI external review (trg-18da39b0): a bare suffix-string tail sorts
    ``'1.0.0-rc1'`` (tail ``'-rc1'``) AFTER ``'1.0.0'`` (tail ``''``), since
    any non-empty string beats ``''`` lexically — the opposite of SemVer,
    where a release outranks every prerelease of the same numeric version.
    The 4th element is therefore "is this a release" (1) vs "is this a
    prerelease" (0), compared BEFORE the suffix text, so the release always
    sorts last among same-triplet names regardless of what the tail says.

    Scope: only the ``-prerelease`` tail is targeted. A ``+build`` metadata
    suffix (which SemVer says must NOT affect precedence at all) is not
    distinguished from a prerelease here and would sort as one — never
    observed in this cache's directory names, so left unhandled rather than
    grown to parse a distinction nothing produces (external review, both
    OpenAI and DeepSeek, iterate-2026-08-05-semver-prerelease-sort).
    """
    m = _SEMVER_RE.match(name)
    if not m:
        return (-1, -1, -1, -1, name)
    suffix = m.group(4) or ""
    return (int(m.group(1)), int(m.group(2)), int(m.group(3)), 0 if suffix else 1, suffix)


def latest_cache_version_dir(plugin_cache_root: Path) -> tuple[Path | None, str]:
    """Newest version subdir under a cached plugin, plus WHY if there is none.

    The cache layout is ``<cache_root>/<plugin-name>/<version>/...``. Returns
    ``(dir, "")`` on success, else ``(None, reason)`` where reason is
    ``absent`` (nothing cached) or ``unreadable`` (the dir exists but could not
    be listed). The caller must keep those apart: "not cached — run
    update-marketplace.sh" is right for the first and actively misleading for
    the second, where the remedy is a permissions fix and any file count the
    check reports would be fabricated rather than measured.
    """
    if not plugin_cache_root.is_dir():
        return None, "absent"
    try:
        versions = sorted(
            (p for p in plugin_cache_root.iterdir() if p.is_dir()),
            key=lambda p: version_key(p.name),
        )
    except OSError:
        return None, "unreadable"
    return (versions[-1], "") if versions else (None, "absent")
