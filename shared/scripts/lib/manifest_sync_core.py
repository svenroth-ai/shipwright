"""Validation, parsing, and write primitives for release manifest syncing.

Shared between ``tools/sync_release_manifests.py`` (the release-time
write/verify tool) and ``tools/verifiers/changelog_checks.py``'s standing
``check_manifest_version_matches_tag`` — one parser, one config reader, so
the preventive gate and the detective check can never disagree about what a
manifest's version field says.

Every failure raises :class:`ManifestSyncError` carrying a ``status`` code
from a closed vocabulary (see class docstring) — callers convert that into
JSON output rather than letting a bare exception escape.
"""

from __future__ import annotations

import json
import posixpath
import re
import stat
import subprocess
from pathlib import Path, PurePosixPath

__all__ = [
    "ManifestSyncError",
    "SUPPORTED_FORMATS",
    "git",
    "git_relative_path",
    "load_declared_manifests",
    "read_manifest_version",
    "render_manifest_write",
    "resolve_contained_path",
    "validate_version",
]

CONFIG_NAME = "shipwright_changelog_config.json"
SUPPORTED_FORMATS = ("package_json",)

#: Bare SemVer 2.0.0 X.Y.Z, no leading "v" — canonical semver.org pattern,
#: rejects leading zeroes (`01.2.3`, `1.2.3-01`) unlike a digit-only regex.
_SEMVER_RE = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-((?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*)"
    r"(?:\.(?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*))*))?"
    r"(?:\+([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?$"
)
_DRIVE_LETTER_RE = re.compile(r"^[A-Za-z]:")


class ManifestSyncError(RuntimeError):
    """A named, fail-closed failure. ``status`` is one of the closed
    vocabulary documented in ``manifest-sync.md``'s status table — never a
    bare unclassified message."""

    def __init__(self, status: str, detail: str, *, path: str | None = None) -> None:
        super().__init__(detail)
        self.status = status
        self.detail = detail
        self.path = path


def validate_version(version: str) -> None:
    """Bare semver, no leading ``v``, no whitespace/control chars.

    Checked before any manifest is touched, in every mode — the same
    string reaches the manifest, the verify-commit comparison, and (with a
    ``v`` prepended) the git tag, so a malformed operator-typed version
    must be rejected up front rather than silently written and then
    "verified" against itself.
    """
    if version != version.strip() or any(ord(c) < 0x20 for c in version):
        raise ManifestSyncError(
            "invalid_version_argument",
            f"version contains whitespace/control characters: {version!r}",
        )
    if version[:1] in ("v", "V"):
        raise ManifestSyncError(
            "invalid_version_argument",
            f"version must not carry a leading 'v' (the tag adds it): {version!r}",
        )
    if not _SEMVER_RE.match(version):
        raise ManifestSyncError(
            "invalid_version_argument", f"not a bare semver X.Y.Z: {version!r}"
        )


def git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """``git -C <root> <args>`` — never a shell, never a bare relative cwd."""
    return subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=10, check=False,
    )


def git_relative_path(root: Path, project_relative_path: str) -> str:
    """Resolve a path relative to ``root`` into a path relative to the git
    root, via ``git rev-parse --show-prefix``.

    ``root`` (the release's ``--project-root``) need not equal the git
    root — a project can live in a subdirectory of its repository. Falls
    back to ``project_relative_path`` unchanged if git metadata can't be
    read (e.g. no git repo at all), which is also correct when the two
    roots coincide, the common case.
    """
    proc = git(root, "rev-parse", "--show-prefix")
    prefix = proc.stdout.strip().replace("\\", "/") if proc.returncode == 0 else ""
    posix_rel = project_relative_path.replace("\\", "/")
    return f"{prefix}{posix_rel}" if prefix else posix_rel


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


def read_manifest_version(text: str, fmt: str) -> str:
    """Parse manifest ``text`` and return its top-level ``version`` string.

    Only ``package_json`` is implemented. A duplicate top-level
    ``"version"`` key is refused (``ambiguous_manifest_structure``) rather
    than silently taking whichever value Python's JSON decoder happened to
    keep — the check is scoped to the ROOT object's own keys, not every
    nested ``"version"`` field a manifest might legitimately carry
    elsewhere (e.g. inside a tool's own nested config block).
    """
    if fmt not in SUPPORTED_FORMATS:
        raise ManifestSyncError("unsupported_format", f"format {fmt!r} is not supported")

    object_pairs: list[list[tuple[str, object]]] = []

    def _hook(pairs: list[tuple[str, object]]) -> dict:
        object_pairs.append(pairs)
        return dict(pairs)

    try:
        parsed = json.loads(text, object_pairs_hook=_hook)
    except json.JSONDecodeError as exc:
        raise ManifestSyncError("parse_error", f"invalid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ManifestSyncError("parse_error", "manifest root must be a JSON object")

    if object_pairs:
        # object_pairs_hook fires innermost-object-first; the ROOT object's
        # own pairs are therefore the LAST call, never a nested object's.
        root_pairs = object_pairs[-1]
        version_key_count = sum(1 for k, _ in root_pairs if k == "version")
        if version_key_count > 1:
            raise ManifestSyncError(
                "ambiguous_manifest_structure", 'duplicate top-level "version" key'
            )

    if "version" not in parsed:
        raise ManifestSyncError("missing_version_field", 'no top-level "version" key')
    version = parsed["version"]
    if not isinstance(version, str):
        raise ManifestSyncError(
            "invalid_version_type", f'"version" is not a string: {version!r}'
        )
    return version


def render_manifest_write(
    original_text: str, fmt: str, current_version: str, new_version: str
) -> tuple[str, bool]:
    """Return ``(new_text, reformatted)``.

    Prefers a surgical single-value substitution — the exact
    ``"version": "<current>"`` span, escaped so semver's ``.``/``-``/``+``
    can't be misread as regex metacharacters — which preserves every other
    byte of ``original_text`` as given (callers must read the file with
    ``read_bytes().decode()``, never ``read_text()``, which folds CRLF to
    LF before this function sees it). Falls back to a full ``json.dump``
    re-render (``reformatted=True``) when that span isn't uniquely
    locatable (0 or 2+ occurrences), so the caller can surface a whole-file
    rewrite instead of a one-line diff.
    """
    if fmt not in SUPPORTED_FORMATS:
        raise ManifestSyncError("unsupported_format", f"format {fmt!r} is not supported")

    pattern = re.compile(r'("version"\s*:\s*")' + re.escape(current_version) + r'(")')
    matches = list(pattern.finditer(original_text))
    if len(matches) == 1:
        m = matches[0]
        new_text = (
            original_text[: m.start()] + m.group(1) + new_version + m.group(2)
            + original_text[m.end():]
        )
        return new_text, False

    parsed = json.loads(original_text)
    parsed["version"] = new_version
    rendered = json.dumps(parsed, indent=2, ensure_ascii=False)
    if not rendered.endswith("\n"):
        rendered += "\n"
    return rendered, True
