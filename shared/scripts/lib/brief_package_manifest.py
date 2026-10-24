"""Brief package core: walk, manifest, hash (campaign brief-driven-run, D1).

Import :mod:`lib.brief_package` -- this module is its implementation half, split out
to keep both files small. The layout validator lives there.


A *Brief package* is the committed directory (default ``<project>/brief/``) an
operator hands ``/shipwright-run``: ``brief.json`` (v2), ``brief.md``,
``scope.md``, ``screen-map.json``, ``chat-map.json`` (chat-first only),
``mockups/``, ``visual-guidelines.md`` and optional ``inputs/``. ``evidence/`` is
never part of the package.

This module is the ONE implementation of what follows; later units import it and
never re-implement it:

* :func:`validate_layout` -- structural defects, as a list (empty = accepted).
* :func:`iter_package_files` -- the files that belong to the package (links,
  junctions, ``evidence/`` and OS junk are never yielded, and never descended into).
* :func:`package_sha256` -- a hash over a manifest (POSIX relative path -> SHA-256
  per file, NFC, sorted). Text files are hashed after CRLF->LF so an LF and a CRLF
  checkout hash the same. ``brief.json`` is hashed as canonical JSON WITHOUT
  ``package_sha256`` / ``approved_by`` / ``approved_at``, so every other field
  (``autonomy``, ``allow_parallel_builders``, ``deploy_target``...) is protected.
* :func:`verify_hash` -- recorded hash vs. recomputed hash.

The hash proves the package is **unchanged since approval**, not that a person
approved it: any agent can recompute it.
"""

from __future__ import annotations

import hashlib
import json
import os
import unicodedata
from collections.abc import Iterator
from pathlib import Path, PurePosixPath

BRIEF_VERSION = 2
#: Excluded from the hash and never read by a phase (matched case-insensitively).
EXCLUDED_TOP_DIRS = frozenset({"evidence"})
#: Operating-system litter that must not change the hash.
JUNK_NAMES = frozenset({".ds_store", "thumbs.db", "desktop.ini", ".gitkeep"})
JUNK_DIRS = frozenset({"__macosx", ".git"})
#: Consent/approval fields removed from ``brief.json`` before hashing.
HASH_EXCLUDED_BRIEF_KEYS = frozenset({"package_sha256", "approved_by", "approved_at"})
#: A file is text (CRLF->LF before hashing) when its first 8 KiB hold no NUL byte and the
#: whole file is valid UTF-8; anything else is hashed byte-exact. Content, not extension,
#: decides, so a ``.tsx`` or extensionless file normalises like a ``.md``.
_SNIFF_BYTES = 8192

class PathCollision(ValueError):
    """Two packaged files collapse to one NFC path or differ only by case."""


def _is_text(raw: bytes) -> bool:
    if 0 in raw[:_SNIFF_BYTES]:
        return False
    try:
        raw.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True


def _is_link(path: Path, root: Path) -> bool:
    """A symlink, or anything reached through a link/junction (Windows junctions included).

    ``root`` must already be resolved. A path is plain when it resolves to exactly
    ``root / <its relative path>``.
    """
    if path.is_symlink():
        return True
    try:
        return path.resolve() != root / path.relative_to(root)
    except (OSError, ValueError):
        return True


def _is_junk(rel: PurePosixPath) -> bool:
    parts = [p.lower() for p in rel.parts]
    return (parts[-1] in JUNK_NAMES or parts[-1].startswith("._")
            or any(p in JUNK_DIRS for p in parts[:-1]))


def _excluded(rel: PurePosixPath) -> bool:
    return rel.parts[0].lower() in EXCLUDED_TOP_DIRS or _is_junk(rel)


def _walk(root: Path) -> tuple[list[Path], list[str]]:
    """``(files, links)`` below ``root``; a link or junction is reported once, never entered."""
    resolved = root.resolve()
    files: list[Path] = []
    links: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        here = Path(dirpath)
        plain = []
        for name in dirnames:
            if _is_link(here / name, resolved):
                links.append((here / name).relative_to(root).as_posix())
            else:
                plain.append(name)
        dirnames[:] = plain
        for name in filenames:
            if _is_link(here / name, resolved):
                links.append((here / name).relative_to(root).as_posix())
            else:
                files.append(here / name)
    return files, links


def iter_package_files(brief_dir: Path) -> Iterator[tuple[str, Path]]:
    """Yield ``(NFC POSIX relative path, path)`` for every file that belongs to the package."""
    root = Path(brief_dir)
    for path in _walk(root)[0]:
        rel = PurePosixPath(*path.relative_to(root).parts)
        if not _excluded(rel):
            yield unicodedata.normalize("NFC", rel.as_posix()), path


def _canonical_json(obj: object) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _load_brief(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise ValueError("brief.json must be a JSON object")
    return data


def _file_digest(path: Path) -> str:
    raw = path.read_bytes()
    if _is_text(raw):
        raw = raw.replace(b"\r\n", b"\n")
    return hashlib.sha256(raw).hexdigest()


def manifest(brief_dir: Path) -> dict[str, str]:
    """NFC POSIX relative path -> SHA-256 for every packaged file, sorted by path.

    Links are skipped here (``validate_layout`` rejects them and :func:`verify_hash`
    fails on them, so a skipped link can never hide content in an accepted package).
    Text (by content, see ``_is_text``) is hashed after CRLF->LF; everything else
    byte-exact. Raises ``PathCollision`` when two files collapse to one NFC path or
    differ only by case, and ``ValueError`` when ``brief.json`` is not a JSON object.
    """
    out: dict[str, str] = {}
    seen: set[str] = set()
    for key, path in iter_package_files(brief_dir):
        if key.casefold() in seen:
            raise PathCollision(f"two files collide on a case-insensitive filesystem: {key!r}")
        seen.add(key.casefold())
        if key == "brief.json":
            brief = {k: v for k, v in _load_brief(path).items() if k not in HASH_EXCLUDED_BRIEF_KEYS}
            out[key] = hashlib.sha256(_canonical_json(brief)).hexdigest()
        else:
            out[key] = _file_digest(path)
    return dict(sorted(out.items()))


def _digest(files: dict[str, str]) -> str:
    return hashlib.sha256(_canonical_json(files)).hexdigest()


def package_sha256(brief_dir: Path) -> str:
    """One SHA-256 over the manifest of ``brief_dir``."""
    return _digest(manifest(brief_dir))


def verify_hash(brief_dir: Path) -> tuple[bool, str]:
    """``(True, "")`` when ``brief.json``'s recorded ``package_sha256`` matches.

    Fails when the package holds a link or junction (its target is outside the
    hash). Trust anchor: the recorded hash lives INSIDE the package, so this detects
    an edit of the content or consent fields since the hash was recorded, not a
    rewrite of the whole directory (hash included). Callers that need that
    (approval) compare against a hash they hold outside the package.
    """
    try:
        if _walk(Path(brief_dir))[1]:
            return False, "package contains links or junctions"
        recorded = _load_brief(Path(brief_dir) / "brief.json").get("package_sha256")
        actual = package_sha256(brief_dir)
    except (OSError, ValueError) as exc:
        return False, f"unreadable package: {exc}"
    if not isinstance(recorded, str) or not recorded:
        return False, "brief.json has no package_sha256"
    if recorded != actual:
        return False, f"package_sha256 mismatch (recorded {recorded[:12]}..., actual {actual[:12]}...)"
    return True, ""
