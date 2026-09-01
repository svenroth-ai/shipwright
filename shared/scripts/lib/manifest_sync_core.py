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
import re
import subprocess
from pathlib import Path

from .manifest_sync_errors import ManifestSyncError
from .manifest_sync_marketplace import (
    find_stale_plugin_entries,
    render_marketplace_write,
    validate_marketplace_structure,
)
from .manifest_sync_paths import CONFIG_NAME, load_declared_manifests, resolve_contained_path

__all__ = [
    "ManifestSyncError",
    "SUPPORTED_FORMATS",
    "CONFIG_NAME",
    "describe_version_state",
    "git",
    "git_relative_path",
    "load_declared_manifests",
    "read_manifest_version",
    "render_manifest_write",
    "resolve_contained_path",
    "validate_version",
]

SUPPORTED_FORMATS = ("package_json", "marketplace_json")

#: Bare SemVer 2.0.0 X.Y.Z, no leading "v" — canonical semver.org pattern,
#: rejects leading zeroes (`01.2.3`, `1.2.3-01`) unlike a digit-only regex.
_SEMVER_RE = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-((?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*)"
    r"(?:\.(?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*))*))?"
    r"(?:\+([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?$"
)
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


def read_manifest_version(text: str, fmt: str) -> str:
    """Parse manifest ``text`` and return its top-level ``version`` string.

    ``package_json`` (a single top-level field) and ``marketplace_json`` (the
    same top-level field, plus a ``plugins`` array of entries each carrying
    their own) are implemented. A duplicate top-level ``"version"`` key is
    refused (``ambiguous_manifest_structure``) rather than silently taking
    whichever value Python's JSON decoder happened to keep — the check is
    scoped to the ROOT object's own keys, not every nested ``"version"``
    field a manifest might legitimately carry elsewhere (e.g. inside a
    tool's own nested config block, or — for ``marketplace_json`` — inside
    each ``plugins[]`` entry).
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

    if fmt == "marketplace_json":
        validate_marketplace_structure(parsed)

    return version


def describe_version_state(text: str, fmt: str, target_version: str) -> tuple[bool, str]:
    """``(matches, detail)`` — whether ``text`` is ALREADY fully at
    ``target_version``, and if not, why.

    For ``package_json`` this is just ``read_manifest_version(...) ==
    target_version`` — one field, one comparison. For ``marketplace_json``
    it is stricter: the root field can equal ``target_version`` while one
    or more ``plugins[]`` entries are still stranded at an older value (a
    partial earlier sync, or a hand-edit) — exactly the drift class this
    format exists to close. A caller comparing only the return of
    ``read_manifest_version`` would call such a manifest "current" and
    both skip re-writing it and pass a commit-verification check over it,
    silently reintroducing the stranded-plugin regression this tool was
    built to prevent. ``detail`` is empty iff ``matches`` is True.
    """
    version = read_manifest_version(text, fmt)
    if version != target_version:
        return False, f"committed version {version!r} != released {target_version!r}"
    if fmt == "marketplace_json":
        stale = find_stale_plugin_entries(json.loads(text), target_version)
        if stale:
            return False, (
                f"root version {target_version!r} matches, but plugins entries "
                f"still carry a different version: {', '.join(stale)}"
            )
    return True, ""


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

    if fmt == "marketplace_json":
        return render_marketplace_write(original_text, current_version, new_version)

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
