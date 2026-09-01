"""Config loading and path-containment primitives for release manifest
syncing — split out of ``manifest_sync_core.py`` to keep it under the
project's 300-line guideline. Re-exported from there, so every existing
consumer's ``from lib.manifest_sync_core import ...`` keeps working
unchanged.
"""

from __future__ import annotations

import json
import posixpath
import stat
from pathlib import Path, PurePosixPath

from .manifest_sync_errors import ManifestSyncError

__all__ = ["CONFIG_NAME", "load_declared_manifests", "resolve_contained_path"]

CONFIG_NAME = "shipwright_changelog_config.json"

_DRIVE_LETTER_RE = __import__("re").compile(r"^[A-Za-z]:")


def _canonicalize(raw_path: str) -> str:
    """Fold ``./`` prefixes and ``..`` segments so aliases like
    ``a/../package.json`` and ``package.json`` dedupe to the same key —
    duplicate-path detection must compare where a path actually points,
    not its literal spelling."""
    posix = raw_path.replace("\\", "/")
    normalized = posixpath.normpath(posix)
    return PurePosixPath(normalized).as_posix()


def load_declared_manifests(project_root: Path) -> list[dict]:
    """The validated, canonicalized ``published_manifests`` list.

    An absent config file, a null/absent ``published_manifests``, or an
    empty list all mean "no manifests declared" — a legitimate no-op,
    returned as ``[]``, never an error. Anything else malformed raises
    :class:`ManifestSyncError` (``invalid_config`` / ``duplicate_manifest_path``)
    fail-closed, since this config is read even from projects
    ``/shipwright-adopt`` runs against untrusted brownfield repos.
    """
    config_path = project_root / CONFIG_NAME
    if not config_path.is_file():
        return []
    try:
        raw = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ManifestSyncError("invalid_config", f"{CONFIG_NAME}: {exc}") from exc
    if raw is None:
        return []
    if not isinstance(raw, dict):
        raise ManifestSyncError("invalid_config", f"{CONFIG_NAME} must be a JSON object")
    declared = raw.get("published_manifests")
    if declared is None:
        return []
    if not isinstance(declared, list):
        raise ManifestSyncError("invalid_config", "published_manifests must be a JSON array")

    entries: list[dict] = []
    seen: dict[str, str] = {}
    for i, item in enumerate(declared):
        if not isinstance(item, dict):
            raise ManifestSyncError("invalid_config", f"published_manifests[{i}] must be an object")
        raw_path = item.get("path")
        fmt = item.get("format")
        if not isinstance(raw_path, str) or not raw_path:
            raise ManifestSyncError(
                "invalid_config", f"published_manifests[{i}].path must be a non-empty string"
            )
        if not isinstance(fmt, str) or not fmt:
            raise ManifestSyncError(
                "invalid_config", f"published_manifests[{i}].format must be a non-empty string"
            )
        canonical = _canonicalize(raw_path)
        if canonical in seen:
            raise ManifestSyncError(
                "duplicate_manifest_path",
                f"{raw_path!r} and {seen[canonical]!r} both resolve to {canonical!r}",
            )
        seen[canonical] = raw_path
        entries.append({"path": canonical, "format": fmt})
    return entries


def _is_reparse_point(path: Path) -> bool:
    """A Windows junction ``Path.is_symlink()`` misses (CPython only sets
    ``S_IFLNK`` for ``IO_REPARSE_TAG_SYMLINK``, not ``_MOUNT_POINT``) — and
    ``mklink /J`` needs no admin/Developer Mode, unlike a real symlink."""
    try:
        attrs = path.lstat().st_file_attributes
    except (AttributeError, OSError):
        return False
    return bool(attrs & stat.FILE_ATTRIBUTE_REPARSE_POINT)


def resolve_contained_path(project_root: Path, rel_path: str) -> Path:
    """Resolve ``rel_path`` under ``project_root``, refusing escape or a
    symlink/junction anywhere along the way — in-root too, not just
    escaping: ``git add`` stages the link entry, not the resolved target's
    changed blob, letting worktree and committed content diverge. Then
    confirms the resolved path still falls under the (symlink-resolved)
    root, belt-and-suspenders against a ``..``-escape the walk missed.
    """
    if PurePosixPath(rel_path).is_absolute() or _DRIVE_LETTER_RE.match(rel_path):
        raise ManifestSyncError(
            "path_outside_project", f"absolute path not allowed: {rel_path}", path=rel_path
        )
    project_root_resolved = project_root.resolve()
    cursor = project_root_resolved
    for part in PurePosixPath(rel_path).parts:
        cursor = cursor / part
        if cursor.is_symlink() or _is_reparse_point(cursor):
            raise ManifestSyncError(
                "path_is_symlink", f"{rel_path} contains a symlink at {part!r}", path=rel_path
            )
    candidate = project_root / rel_path
    resolved = candidate.resolve()
    try:
        resolved.relative_to(project_root_resolved)
    except ValueError:
        raise ManifestSyncError(
            "path_outside_project", f"{rel_path} resolves outside the project root", path=rel_path
        ) from None
    return candidate
