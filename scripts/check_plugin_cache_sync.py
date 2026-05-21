#!/usr/bin/env python3
"""Detect drift between the local plugin cache and the repo HEAD.

Iterate C.3 (ADR-061) — closes the open gap from CLAUDE.md's
"plugin-side fixes silently never take effect" learning: changes
under ``plugins/*`` and ``shared/scripts/`` aren't auto-synced to
the runtime cache at ``~/.claude/plugins/cache/shipwright/`` unless
``scripts/update-marketplace.sh`` is run. Iterates 7-11 all had
plugin-side fixes that landed in the dev repo but never reached
runtime because the sync step was skipped.

This script walks every ``plugins/shipwright-*`` directory under
the repo root, locates the corresponding latest version directory
under the cache, and compares each tracked file by SHA-256. Drift
surfaces as a WARN line on stderr; exit code is 0 except when
``--strict`` is passed (which exits 1 on any drift).

CI-safe: when ``~/.claude/`` doesn't exist (typical in CI runners),
the script no-ops with status ``cache_root_absent``.

Usage:
    uv run scripts/check_plugin_cache_sync.py [--strict] [--json]
    uv run scripts/check_plugin_cache_sync.py --cache-root <path> --repo-root <path>
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

# Files we compare. The plugin-cache sync ships SKILL.md, scripts,
# hooks, agents, references, schemas. We DON'T compare __pycache__,
# .pyc, or anything under .git/.venv/etc. — those are build artifacts.
_TRACKED_SUFFIXES = (".py", ".md", ".json", ".sh", ".ps1", ".yml", ".yaml")
_SKIP_DIRS = {"__pycache__", ".git", ".venv", "venv", "node_modules",
              ".pytest_cache", "dist", "build"}


def _default_cache_root() -> Path:
    return Path.home() / ".claude" / "plugins" / "cache" / "shipwright"


def _default_repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


# Text suffixes get line-ending normalization (CRLF → LF) before hash
# so a Windows checkout vs a Linux cache doesn't produce false drift
# (reviewer-flagged Gemini-M1). Binary-style suffixes don't normalize.
_TEXT_SUFFIXES = (".py", ".md", ".json", ".sh", ".ps1", ".yml", ".yaml")


def _file_hash(path: Path) -> str | None:
    """SHA-256 hex digest of a file, with CRLF→LF normalization for text.

    Returns ``None`` if unreadable.

    Reviewer-flagged Gemini-M1: a Windows checkout (CRLF) compared
    against a Linux-synced cache (LF) would produce false drift on
    every text file. Solution: open text-suffix files in text mode
    with ``newline=""`` and re-encode line-by-line as UTF-8 with `\\n`
    separators before hashing. Non-text suffixes (none currently in
    ``_TRACKED_SUFFIXES``, but the path stays open for future
    additions) hash byte-exact in 64 KiB chunks.

    Reviewer-flagged OpenAI-M7 / Gemini-S3: refuse to follow
    symlinks. They could escape the plugin root or form loops.
    """
    try:
        if path.is_symlink():
            return None
        h = hashlib.sha256()
        if path.suffix.lower() in _TEXT_SUFFIXES:
            # Text mode with `newline=None` translates `\r\n` and `\r`
            # to `\n` on read (universal newline mode), so the hash is
            # invariant across CRLF / LF / CR checkouts.
            with path.open("r", encoding="utf-8", errors="replace", newline=None) as fp:
                for line in fp:
                    h.update(line.encode("utf-8"))
        else:
            with path.open("rb") as fp:
                for chunk in iter(lambda: fp.read(65536), b""):
                    h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def _walk_tracked_files(root: Path) -> dict[str, str]:
    """Return {relative_posix_path: sha256} for files under root.

    Skips ``_SKIP_DIRS`` and files whose suffix isn't in
    ``_TRACKED_SUFFIXES``. Defensive: any OSError /
    PermissionError raised mid-traversal short-circuits this
    plugin's hash dict but doesn't propagate (reviewer-flagged
    Gemini truncated finding on `rglob` PermissionError + OpenAI's
    "isolate filesystem errors").
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
        if any(part in _SKIP_DIRS for part in rel_parts):
            continue
        if entry.suffix.lower() not in _TRACKED_SUFFIXES:
            continue
        digest = _file_hash(entry)
        if digest is None:
            continue
        rel = entry.relative_to(root).as_posix()
        out[rel] = digest
    return out


_SEMVER_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)(.*)$")


def _version_key(name: str) -> tuple:
    """Numeric-tuple sort key for SemVer-shaped dir names.

    Reviewer-flagged Gemini-S1 + OpenAI-M2: pure lexical sort puts
    `0.10.0` before `0.2.0` (since `'1' < '2'`). Parse the
    leading ``MAJOR.MINOR.PATCH`` triplet as ints; any pre-release /
    suffix stays as a string tail. Non-SemVer names fall back to
    plain string sort via a sentinel low tuple.
    """
    m = _SEMVER_RE.match(name)
    if not m:
        # Sort non-SemVer names before any real version.
        return (-1, -1, -1, name)
    major, minor, patch = int(m.group(1)), int(m.group(2)), int(m.group(3))
    return (major, minor, patch, m.group(4) or "")


def _latest_cache_version_dir(plugin_cache_root: Path) -> Path | None:
    """Pick the newest version subdir under a cached plugin.

    The cache layout is ``<cache_root>/<plugin-name>/<version>/...``.
    Uses SemVer-aware sort so `0.10.0` > `0.2.0` (reviewer-flagged
    Gemini-S1 + OpenAI-M2).
    """
    if not plugin_cache_root.is_dir():
        return None
    versions = sorted(
        (p for p in plugin_cache_root.iterdir() if p.is_dir()),
        key=lambda p: _version_key(p.name),
    )
    if not versions:
        return None
    return versions[-1]


def check_sync(
    *,
    repo_root: Path,
    cache_root: Path,
) -> dict:
    """Compare every ``plugins/shipwright-*`` against its cache equivalent.

    Returns a structured dict:
    - ``status``: ``ok`` | ``drift`` | ``cache_root_absent`` |
      ``no_repo_plugins``.
    - ``plugins``: per-plugin records with the drift state.
    - ``drifted_count``: total plugins with drift.

    Best-effort: no exception leaks out; OSError on cache traversal
    is treated as "plugin not in cache".
    """
    plugins_dir = repo_root / "plugins"
    if not cache_root.is_dir():
        return {"status": "cache_root_absent", "plugins": [], "drifted_count": 0,
                "cache_root": str(cache_root)}
    if not plugins_dir.is_dir():
        return {"status": "no_repo_plugins", "plugins": [], "drifted_count": 0}

    results: list[dict] = []
    drifted = 0
    for plugin_dir in sorted(plugins_dir.iterdir()):
        if not plugin_dir.is_dir() or not plugin_dir.name.startswith("shipwright-"):
            continue
        plugin_name = plugin_dir.name
        plugin_cache = cache_root / plugin_name
        cache_version_dir = _latest_cache_version_dir(plugin_cache)
        if cache_version_dir is None:
            results.append({
                "plugin": plugin_name,
                "state": "not_in_cache",
                "detail": f"no cached version under {plugin_cache}",
            })
            drifted += 1
            continue

        repo_hashes = _walk_tracked_files(plugin_dir)
        cache_hashes = _walk_tracked_files(cache_version_dir)
        # Drift = ANY repo file whose cache equivalent is missing or
        # hashes differently. Files in cache but not in repo are
        # operator/plugin-side artifacts (e.g. cached pyproject
        # lockfile) and don't count as drift.
        diffs = [
            rel for rel in repo_hashes
            if cache_hashes.get(rel) != repo_hashes[rel]
        ]
        missing_in_cache = [
            rel for rel in repo_hashes if rel not in cache_hashes
        ]
        # Reviewer-flagged OpenAI-L12: include scan-context counts so
        # the operator can tell trivial from significant drift.
        if diffs:
            results.append({
                "plugin": plugin_name,
                "state": "drift",
                "cache_version": cache_version_dir.name,
                "tracked_count": len(repo_hashes),
                "diff_count": len(diffs),
                "missing_in_cache_count": len(missing_in_cache),
                "sample": diffs[:5],
            })
            drifted += 1
        else:
            results.append({
                "plugin": plugin_name,
                "state": "ok",
                "cache_version": cache_version_dir.name,
                "tracked_count": len(repo_hashes),
            })

    status = "drift" if drifted else "ok"
    return {
        "status": status,
        "drifted_count": drifted,
        "plugins": results,
        "cache_root": str(cache_root),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Plugin-cache vs repo sync check")
    parser.add_argument("--repo-root", default=str(_default_repo_root()))
    parser.add_argument("--cache-root", default=str(_default_cache_root()))
    parser.add_argument("--strict", action="store_true",
                        help="Exit 1 on any drift (default: fail-soft WARN, exit 0).")
    parser.add_argument("--json", action="store_true",
                        help="Emit structured JSON on stdout instead of human prose.")
    args = parser.parse_args(argv)

    result = check_sync(
        repo_root=Path(args.repo_root),
        cache_root=Path(args.cache_root),
    )

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        status = result["status"]
        if status == "cache_root_absent":
            print(f"plugin-cache-sync: skip — {result['cache_root']} doesn't exist (CI?)")
        elif status == "no_repo_plugins":
            # Reviewer-flagged code-review-M2: AC-4 says this state must
            # be a no-op-friendly return, not a drift warning. The repo
            # has no `plugins/` dir at all → nothing to compare against.
            print("plugin-cache-sync: skip — no plugins/ dir in repo")
        elif status == "ok":
            print(f"plugin-cache-sync: ok — all {len(result['plugins'])} plugin(s) in sync")
        elif status == "drift":
            print(
                f"plugin-cache-sync: WARN — {result['drifted_count']} plugin(s) drifted. "
                f"Run scripts/update-marketplace.sh to re-sync.",
                file=sys.stderr,
            )
            for entry in result["plugins"]:
                if entry["state"] in ("drift", "not_in_cache"):
                    print(f"  - {entry['plugin']}: {entry}", file=sys.stderr)
        else:
            # Unknown status — print a diagnostic but don't fail.
            print(f"plugin-cache-sync: unknown status {status!r}", file=sys.stderr)

    if args.strict and result["status"] == "drift":
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
