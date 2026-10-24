"""Brief package: layout validator and manifest hash (campaign brief-driven-run, D1).

A *Brief package* is the committed directory (default ``<project>/brief/``) an
operator hands ``/shipwright-run``: ``brief.json`` (v2), ``brief.md``,
``scope.md``, ``screen-map.json``, ``chat-map.json`` (chat-first only),
``mockups/``, ``visual-guidelines.md`` and optional ``inputs/``. ``evidence/`` is
never part of the package.

This is the ONE public surface; later units import it and never re-implement it:

* :func:`validate_layout` -- structural defects, as a list (empty = accepted).
* :func:`iter_package_files` -- the files that belong to the package (links,
  junctions, ``evidence/`` and OS junk are never yielded, and never descended into).
* :func:`package_sha256` / :func:`manifest` -- a hash over a manifest (NFC POSIX
  relative path -> SHA-256 per file, sorted). Text files are hashed after CRLF->LF
  so an LF and a CRLF checkout hash the same. ``brief.json`` is hashed as canonical
  JSON WITHOUT ``package_sha256`` / ``approved_by`` / ``approved_at``, so every other
  field (``autonomy``, ``allow_parallel_builders``, ``deploy_target``...) is protected.
* :func:`verify_hash` -- recorded hash vs. recomputed hash.

The hash proves the package is **unchanged since approval**, not that a person
approved it: any agent can recompute it.
"""

from __future__ import annotations

import unicodedata
from pathlib import Path, PurePosixPath

from .brief_package_manifest import (  # noqa: F401  (re-exported public surface)
    BRIEF_VERSION, HASH_EXCLUDED_BRIEF_KEYS, PathCollision, _excluded, _walk, iter_package_files,
    loads_strict, manifest, package_sha256, verify_hash,
)

REQUIRED_FILES = ("brief.json", "brief.md", "scope.md", "screen-map.json", "visual-guidelines.md")
REQUIRED_BRIEF_KEYS = (
    "version", "profile", "deploy_target", "autonomy", "ux_shape", "source_class",
    "scope", "design_system", "brief_dir", "allow_parallel_builders", "ui_host", "env_preflight",
)
#: String fields that must be non-empty strings.
STRING_BRIEF_KEYS = ("profile", "deploy_target", "source_class", "scope", "design_system", "ui_host")
#: Fields naming a file inside the package.
FILE_REF_KEYS = ("scope", "design_system")
AUTONOMY_VALUES = ("guided", "autonomous", "unattended")
UX_SHAPES = ("classic", "chat-first")


def _issue(code: str, path: str, message: str) -> dict[str, str]:
    return {"code": code, "path": path, "message": message}


def _bad_rel_path(value: object) -> bool:
    """True unless ``value`` is a non-empty, relative, portable, forward-descending path.

    ``:`` is refused anywhere: a drive letter, and on Windows an alternate data
    stream (``notes:x``) holds content the hash never covers.
    """
    if not isinstance(value, str) or not value.strip():
        return True
    norm = value.replace("\\", "/")
    return norm.startswith("/") or ":" in norm or ".." in PurePosixPath(norm).parts


def _in_manifest(ref: str, keys: set[str]) -> bool:
    return unicodedata.normalize("NFC", ref.replace("\\", "/")) in keys


def _check_brief(brief: dict, keys: set[str], issues: list[dict[str, str]]) -> None:
    for key in REQUIRED_BRIEF_KEYS:
        if key not in brief:
            issues.append(_issue("missing_field", "brief.json", f"required field '{key}' is absent"))
    if brief.get("version") != BRIEF_VERSION:
        issues.append(_issue("bad_version", "brief.json", f"version must be {BRIEF_VERSION}"))
    if "autonomy" in brief and brief["autonomy"] not in AUTONOMY_VALUES:
        issues.append(_issue("bad_value", "brief.json", f"autonomy must be one of {AUTONOMY_VALUES}"))
    if "ux_shape" in brief and brief["ux_shape"] not in UX_SHAPES:
        issues.append(_issue("bad_value", "brief.json", f"ux_shape must be one of {UX_SHAPES}"))
    if "allow_parallel_builders" in brief and not isinstance(brief["allow_parallel_builders"], bool):
        issues.append(_issue("bad_value", "brief.json", "allow_parallel_builders must be a boolean"))
    if "env_preflight" in brief and not isinstance(brief["env_preflight"], list):
        issues.append(_issue("bad_value", "brief.json", "env_preflight must be a list"))
    for key in STRING_BRIEF_KEYS:
        if key in brief and not (isinstance(brief[key], str) and brief[key].strip()):
            issues.append(_issue("bad_value", "brief.json", f"{key} must be a non-empty string"))
    for key in FILE_REF_KEYS:
        ref = brief.get(key)
        if isinstance(ref, str) and ref.strip() and (_bad_rel_path(ref) or not _in_manifest(ref, keys)):
            issues.append(_issue("dangling_ref", "brief.json", f"{key} must name a hashed file in the package"))
    if "brief_dir" in brief:
        bdir = brief["brief_dir"]
        parts = PurePosixPath(bdir.replace("\\", "/")).parts if isinstance(bdir, str) else ()
        if _bad_rel_path(bdir) or any(p.lower() == ".shipwright" for p in parts):
            issues.append(_issue("bad_brief_dir", "brief.json",
                                 "brief_dir must be project-relative, committable and not under .shipwright/"))
    sha = brief.get("package_sha256")
    if sha is not None and not (isinstance(sha, str) and len(sha) == 64
                                and all(c in "0123456789abcdef" for c in sha)):
        issues.append(_issue("bad_value", "brief.json", "package_sha256 must be 64 lowercase hex chars"))


def _check_screen_map(data: object, keys: set[str], issues: list[dict[str, str]]) -> None:
    screens = data.get("screens") if isinstance(data, dict) else None
    if not isinstance(screens, list) or not screens:
        issues.append(_issue("bad_screen_map", "screen-map.json", "needs a non-empty 'screens' list"))
        return
    for entry in screens:
        mock = entry.get("mockup") if isinstance(entry, dict) else None
        if _bad_rel_path(mock) or not _in_manifest(f"mockups/{mock}", keys):
            issues.append(_issue("dangling_mockup", "screen-map.json",
                                 f"screen entry references a missing or unhashed mockup {mock!r}"))


def _read_text(f: Path, name: str, issues: list[dict[str, str]]) -> str | None:
    try:
        return f.read_text(encoding="utf-8-sig")
    except (UnicodeDecodeError, OSError) as exc:
        issues.append(_issue("bad_encoding", name, f"not readable as UTF-8 text: {exc}"))
        return None


def validate_layout(brief_dir: Path) -> list[dict[str, str]]:
    """Structural defects of the package at ``brief_dir`` (empty list = accepted).

    Each defect is ``{"code", "path", "message"}``; the function reports, it does
    not raise. Required ``brief.json`` fields: ``REQUIRED_BRIEF_KEYS`` (D1's v2 set
    except the consent/approval trio, which the hash and preflight own). Every
    file reference must name a file the hash covers. Hash freshness is a separate
    question -- see :func:`verify_hash`.
    """
    root = Path(brief_dir)
    if not root.is_dir():
        return [_issue("missing_dir", str(brief_dir), "brief directory does not exist")]
    issues = [_issue("symlink", link, "links and junctions are not allowed") for link in _walk(root)[1]]
    for path in _walk(root)[0]:
        rel = PurePosixPath(*path.relative_to(root).parts)
        quiet = rel.parts[0] == "evidence" or (rel.name == ".gitkeep" and path.stat().st_size == 0)
        if _excluded(rel) and not quiet:
            issues.append(_issue("excluded_content", rel.as_posix(),
                                 "excluded from the hash but present: remove it (a phase could still read it)"))
    keys: set[str] = set()
    try:
        keys = set(manifest(root))
        package_sha256(root)
    except PathCollision as exc:
        issues.append(_issue("path_collision", ".", str(exc)))
        keys = {k for k, _ in iter_package_files(root)}
    except OSError as exc:
        issues.append(_issue("unreadable_file", ".", f"a packaged file cannot be read: {exc}"))
        keys = {k for k, _ in iter_package_files(root)}
    except ValueError as exc:  # also UnicodeEncodeError (lone surrogate in JSON or a file name)
        issues.append(_issue("unhashable_package", ".", f"the package cannot be hashed: {exc}"))
        keys = {k for k, _ in iter_package_files(root)}
    brief: dict | None = None
    for name in REQUIRED_FILES:
        if name not in keys:
            issues.append(_issue("missing_file", name, f"required file '{name}' is absent"))
            continue
        text = _read_text(root / name, name, issues)
        if text is None:
            continue
        if not text.strip():
            issues.append(_issue("empty_file", name, f"'{name}' is empty"))
        elif name.endswith(".json"):
            try:
                data = loads_strict(text)
            except ValueError as exc:
                issues.append(_issue("invalid_json", name, f"not valid JSON: {exc}"))
                continue
            if name == "brief.json" and isinstance(data, dict):
                brief = data
            elif name == "brief.json":
                issues.append(_issue("invalid_json", name, "brief.json must be a JSON object"))
            else:
                _check_screen_map(data, keys, issues)
    if not any(k.startswith("mockups/") for k in keys):
        issues.append(_issue("missing_dir", "mockups", "mockups/ must hold at least one packaged file"))
    if brief is not None:
        _check_brief(brief, keys, issues)
        if brief.get("ux_shape") == "chat-first" and "chat-map.json" not in keys:
            issues.append(_issue("missing_file", "chat-map.json", "chat-first packages need chat-map.json"))
        if brief.get("ux_shape") == "classic" and "chat-map.json" in keys:
            issues.append(_issue("unexpected_file", "chat-map.json", "chat-map.json is chat-first only"))
    return issues
