"""Destructive-write guards for build_codex_plugin.py (M1).

Split out of the builder to keep both files under the project's 300-LOC
source guideline. ``build_bundle`` ``rmtree``s its output directory outright
and overwrites a marketplace manifest in that directory's PARENT — these
guards exist because neither had a check against a colliding/foreign target
(doubt-review, 2026-09-20).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

BUNDLE_NAME = "shipwright"
_BUNDLE_MARKER = Path(".codex-plugin") / "plugin.json"


class UnsafeOutputPathError(RuntimeError):
    """Raised when ``--out`` (or its parent, for the marketplace manifest)
    would make ``build_bundle`` delete or overwrite something it does not
    own — a real risk since it ``rmtree``s its output directory outright
    (doubt-review, 2026-09-20: ``--out .`` from the project root is one typo
    away from the documented invocation)."""


def is_prior_bundle(out_dir: Path) -> bool:
    marker = out_dir / _BUNDLE_MARKER
    if not marker.is_file():
        return False
    try:
        manifest = json.loads(marker.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return False
    return isinstance(manifest, dict) and manifest.get("name") == BUNDLE_NAME


def refuse_symlinked_output_path(out_dir: Path) -> None:
    """Refuse when ``--out`` itself, or any existing ancestor component on
    the way to it, is a symlink. ``build_bundle`` immediately calls
    ``.resolve()`` on ``out_dir``, which transparently follows a symlink to
    whatever it points at — every later check (including
    ``is_prior_bundle``) then operates on that RESOLVED target, so a
    symlinked ``--out`` pointing at some other directory that merely looks
    like a prior bundle would pass every check while the actual rmtree and
    rebuild land somewhere the operator never typed. Must run BEFORE
    ``out_dir`` is resolved (local PR-review preflight, 2026-09-21).
    ``Path.is_symlink()`` returns ``False`` for a component that does not
    exist yet, so walking every parent up to the filesystem root is safe
    without a separate existence check."""
    for candidate in (out_dir, *out_dir.parents):
        if candidate.is_symlink():
            raise UnsafeOutputPathError(
                f"{candidate} is a symlink — refusing to resolve --out through it; "
                "pass the real target path directly."
            )


def refuse_unsafe_output_path(*, project_root: Path, out_dir: Path) -> None:
    if out_dir == project_root or project_root.is_relative_to(out_dir):
        raise UnsafeOutputPathError(
            f"--out {out_dir} would delete the project root ({project_root}) or an "
            "ancestor of it — pass a build-output directory outside the source tree."
        )
    # Checks the marker's own "name" field, not just its presence: a foreign
    # installed Codex plugin also has a `.codex-plugin/plugin.json`, and
    # `--out` pointed at one by mistake must not rmtree someone else's
    # plugin (doubt-review round 2, 2026-09-20).
    if out_dir.exists() and any(out_dir.iterdir()) and not is_prior_bundle(out_dir):
        raise UnsafeOutputPathError(
            f"--out {out_dir} already exists, is non-empty, and does not look like a "
            f"prior build of THIS bundle (missing .codex-plugin/plugin.json with "
            f"\"name\": {BUNDLE_NAME!r}) — refusing to delete a directory this tool "
            "did not create."
        )


class UnsafeSourceSymlinkError(RuntimeError):
    """Raised when a source tree ``_copy_tree`` is about to copy contains a
    symlink. ``shutil.copytree`` defaults to ``symlinks=False``, which
    FOLLOWS a symlink and copies its target's content — so a symlink planted
    inside a plugin's source tree, pointing anywhere on disk, would have that
    target silently bundled with no provenance record, undermining the
    builder's own drift/manifest guarantees (local PR-review preflight,
    2026-09-21)."""


def refuse_symlinks_in_tree(root: Path, *, exclude_dirnames: set[str] | None = None) -> None:
    exclude_dirnames = exclude_dirnames or set()
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in exclude_dirnames]
        for name in (*dirnames, *filenames):
            candidate = Path(dirpath) / name
            if candidate.is_symlink():
                raise UnsafeSourceSymlinkError(
                    f"{candidate} is a symlink — refusing to bundle a source tree "
                    "containing one, since it could point outside the declared source "
                    "with no record of what was actually copied."
                )


def refuse_foreign_marketplace(marketplace_path: Path) -> None:
    # Checked BEFORE is_file()/read_text(), which both follow a symlink: this
    # builder only ever creates marketplace.json as a plain file via
    # write_text, so a symlink at this exact path is never one it made,
    # regardless of what its target contains — accepting one on content alone
    # would let write_text's own symlink-following overwrite an arbitrary
    # target outside marketplace_dir (local PR-review preflight, 2026-09-21).
    if marketplace_path.is_symlink():
        raise UnsafeOutputPathError(
            f"{marketplace_path} is a symlink — refusing to write through it to "
            "whatever it points at."
        )
    if not marketplace_path.exists():
        return
    # A directory (or other special file) at this exact path is not
    # something this builder ever created — the sole write site is a plain
    # write_text call, which raises an uncaught IsADirectoryError on a
    # directory target instead of failing cleanly (local PR-review
    # preflight, 2026-09-21).
    if not marketplace_path.is_file():
        raise UnsafeOutputPathError(
            f"{marketplace_path} already exists and is not a regular file — refusing "
            "to write a marketplace manifest there."
        )
    try:
        existing = json.loads(marketplace_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        existing = None
    if not isinstance(existing, dict) or existing.get("name") != BUNDLE_NAME:
        raise UnsafeOutputPathError(
            f"{marketplace_path} already exists and is not a marketplace manifest this "
            f"tool owns (expected top-level \"name\": {BUNDLE_NAME!r}) — refusing to "
            "overwrite it."
        )
