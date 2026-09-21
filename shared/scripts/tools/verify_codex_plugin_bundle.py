#!/usr/bin/env python3
"""Drift/verifier for the Codex plugin bundle (M1, AC5).

Rebuilds the bundle fresh into a throwaway directory and diffs its file-hash
tree against the live bundle directory being checked. This never trusts the
live bundle's own ``BUILD_MANIFEST.json`` (which could itself be stale or
hand-edited) — the fresh rebuild IS the ground truth, exactly what
``build_codex_plugin.py``'s own AC4 byte-identical-rebuild guarantee
promises: same source in, same bytes out, every time.

Three drift classes:

- **stale** — a file exists in both trees but its content hash differs
  (source changed after the bundle was last built).
- **missing** — a file a fresh rebuild would produce is absent from the
  live bundle (source added, bundle never rebuilt).
- **undeclared** — a file exists in the live bundle but a fresh rebuild
  would not produce it (hand-edited content, a path escape, or leftover
  cruft from a source file since deleted).

Usage:
    uv run shared/scripts/tools/verify_codex_plugin_bundle.py \\
        --project-root . --bundle-dir dist/codex-plugin
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from build_codex_plugin import (
    BundleCollisionError,
    UnsafeOutputPathError,
    UnsafeSourceSymlinkError,
    _hash_tree,
    build_bundle,
)


@dataclass
class VerifyResult:
    ok: bool
    stale_files: list[str] = field(default_factory=list)
    missing_files: list[str] = field(default_factory=list)
    undeclared_files: list[str] = field(default_factory=list)


def verify_bundle(*, project_root: Path, bundle_dir: Path) -> VerifyResult:
    project_root = Path(project_root).resolve()
    bundle_dir = Path(bundle_dir).resolve()

    with tempfile.TemporaryDirectory(prefix="codex-plugin-verify-") as tmp:
        fresh_dir = Path(tmp) / "fresh"
        build_bundle(project_root=project_root, out_dir=fresh_dir)
        fresh_hashes = _hash_tree(fresh_dir)

    live_hashes = _hash_tree(bundle_dir)

    stale = sorted(
        f for f in fresh_hashes
        if f in live_hashes and live_hashes[f] != fresh_hashes[f]
    )
    missing = sorted(f for f in fresh_hashes if f not in live_hashes)
    undeclared = sorted(f for f in live_hashes if f not in fresh_hashes)

    return VerifyResult(
        ok=not (stale or missing or undeclared),
        stale_files=stale,
        missing_files=missing,
        undeclared_files=undeclared,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", default=".", help="Monorepo root (default: cwd)")
    parser.add_argument("--bundle-dir", required=True, help="Existing bundle directory to verify")
    args = parser.parse_args(argv)

    try:
        result = verify_bundle(
            project_root=Path(args.project_root), bundle_dir=Path(args.bundle_dir)
        )
    except (BundleCollisionError, UnsafeOutputPathError, UnsafeSourceSymlinkError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if result.ok:
        print("OK: bundle matches a fresh rebuild from source.")
        return 0

    if result.stale_files:
        print("STALE (source changed, bundle not rebuilt):", file=sys.stderr)
        for f in result.stale_files:
            print(f"  {f}", file=sys.stderr)
    if result.missing_files:
        print("MISSING (source added, bundle not rebuilt):", file=sys.stderr)
        for f in result.missing_files:
            print(f"  {f}", file=sys.stderr)
    if result.undeclared_files:
        print("UNDECLARED (not traceable to any declared source):", file=sys.stderr)
        for f in result.undeclared_files:
            print(f"  {f}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
