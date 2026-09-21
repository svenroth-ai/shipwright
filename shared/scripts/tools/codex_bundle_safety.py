"""Destructive-write guards for build_codex_plugin.py (M1).

Split out of the builder to keep both files under the project's 300-LOC
source guideline. ``build_bundle`` ``rmtree``s its output directory outright
and overwrites a marketplace manifest in that directory's PARENT — these
guards exist because neither had a check against a colliding/foreign target
(doubt-review, 2026-09-20).
"""

from __future__ import annotations

import json
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


def refuse_foreign_marketplace(marketplace_path: Path) -> None:
    if not marketplace_path.is_file():
        return
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
