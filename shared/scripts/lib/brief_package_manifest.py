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
from typing import NamedTuple

BRIEF_VERSION = 2
#: Excluded from the hash and never read by a phase (matched case-insensitively).
EXCLUDED_TOP_DIRS = frozenset({"evidence"})
#: Operating-system litter that must not change the hash.
JUNK_NAMES = frozenset({".ds_store", "thumbs.db", "desktop.ini", ".gitkeep"})
JUNK_DIRS = frozenset({"__macosx", ".git"})
#: File-manager metadata nothing reads as content: excluded from the hash and not reported.
METADATA_NAMES = frozenset({".ds_store", "thumbs.db", "desktop.ini"})
#: Consent/approval fields removed from ``brief.json`` before hashing.
HASH_EXCLUDED_BRIEF_KEYS = frozenset({"package_sha256", "approved_by", "approved_at"})
#: A file is text (CRLF->LF before hashing) when its first 8000 bytes hold no NUL byte --
#: git's own heuristic, so a checkout with ``core.autocrlf`` hashes the same as one without.
#: Content, not extension, decides (a ``.tsx`` or extensionless file normalises like a ``.md``).
_SNIFF_BYTES = 8000

class PathCollision(ValueError):
    """Two packaged files collapse to one NFC path or differ only by case."""


def _is_text(raw: bytes) -> bool:
    return 0 not in raw[:_SNIFF_BYTES]


def _plain(path: Path) -> Path:
    """``path.resolve()`` without the Windows extended-length prefix (``\\\\?\\``), which
    ``resolve()`` adds to long paths and which would make every path look like a link."""
    text = str(path)
    if text.startswith("\\\\?\\UNC\\"):
        return Path("\\\\" + text[8:])
    if text.startswith("\\\\?\\"):
        return Path(text[4:])
    return path


def _is_link(path: Path, root: Path) -> bool:
    """A symlink, or anything reached through a link/junction (Windows junctions included).

    ``root`` must already be resolved. A path is plain when it resolves to exactly
    ``root / <its relative path>``.
    """
    if path.is_symlink():
        return True
    try:
        return _plain(path.resolve()) != root / path.relative_to(root)
    except (OSError, ValueError):
        return True


def _is_junk(rel: PurePosixPath) -> bool:
    parts = [p.lower() for p in rel.parts]
    return (parts[-1] in JUNK_NAMES or parts[-1].startswith("._")
            or any(p in JUNK_DIRS for p in parts[:-1]))


def _excluded(rel: PurePosixPath) -> bool:
    return rel.parts[0].lower() in EXCLUDED_TOP_DIRS or _is_junk(rel)


class PackageUnreadable(OSError):
    """A directory or file of the package could not be read."""


class Scan(NamedTuple):
    """One walk of a package: the resolved root, plain files, links, read errors."""

    root: Path
    files: list[Path]
    links: list[str]
    errors: list[str]


def scan_package(brief_dir: Path) -> Scan:
    """Walk ``brief_dir`` once. The root is resolved first and the RESOLVED path is
    walked, so a relative root, a Windows 8.3 short name or a linked parent directory
    all behave like the plain absolute path. A link or junction below the root is
    reported once and never entered; an unreadable directory is recorded in ``errors``."""
    root = _plain(Path(brief_dir).resolve())
    files: list[Path] = []
    links: list[str] = []
    errors: list[str] = []

    def onerror(exc: OSError) -> None:
        errors.append(f"{exc.filename}: {exc.strerror or exc}")

    for dirpath, dirnames, filenames in os.walk(root, followlinks=False, onerror=onerror):
        here = Path(dirpath)
        plain = []
        for name in dirnames:
            if _is_link(here / name, root):
                links.append((here / name).relative_to(root).as_posix())
            else:
                plain.append(name)
        if here == root and "evidence" in plain:
            plain.remove("evidence")  # never read by a phase: not walked, not hashed
        dirnames[:] = plain
        for name in filenames:
            if _is_link(here / name, root):
                links.append((here / name).relative_to(root).as_posix())
            else:
                files.append(here / name)
    return Scan(root, files, links, errors)


def _quiet_exclusion(rel: PurePosixPath, path: Path) -> bool:
    """Excluded entries that need no report: the exact-case ``evidence/`` top dir, file-manager
    metadata (``METADATA_NAMES``) and an empty ``.gitkeep``."""
    if rel.parts[0] == "evidence" or rel.name.lower() in METADATA_NAMES:
        return True
    try:
        return rel.name == ".gitkeep" and path.stat().st_size == 0
    except OSError:
        return False


def unreported_exclusions(found: Scan) -> list[str]:
    """Paths excluded from the hash that are nevertheless present (a phase could read them)."""
    out = []
    for path in found.files:
        rel = PurePosixPath(*path.relative_to(found.root).parts)
        if _excluded(rel) and not _quiet_exclusion(rel, path):
            out.append(rel.as_posix())
    return out


def iter_package_files(brief_dir: Path) -> Iterator[tuple[str, Path]]:
    """Yield ``(NFC POSIX relative path, path)`` for every file that belongs to the package.

    Raises ``PackageUnreadable`` when a directory could not be read (a skipped directory
    would silently shorten the package)."""
    found = scan_package(brief_dir)
    if found.errors:
        raise PackageUnreadable("; ".join(found.errors))
    yield from _package_files(found)


def _package_files(found: Scan) -> Iterator[tuple[str, Path]]:
    for path in found.files:
        rel = PurePosixPath(*path.relative_to(found.root).parts)
        if not _excluded(rel):
            yield unicodedata.normalize("NFC", rel.as_posix()), path


def _canonical_json(obj: object) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _no_duplicate_keys(pairs: list[tuple[str, object]]) -> dict:
    out: dict = {}
    for key, value in pairs:
        if key in out:
            raise ValueError(f"duplicate JSON key {key!r}")
        out[key] = value
    return out


def loads_strict(text: str) -> object:
    """``json.loads`` that refuses duplicate keys (a raw-text reader and a parser would
    disagree on them) and turns absurd nesting into a ``ValueError``."""
    try:
        return json.loads(text, object_pairs_hook=_no_duplicate_keys)
    except RecursionError as exc:
        raise ValueError("JSON nesting is too deep") from exc


def _load_brief(path: Path) -> dict:
    data = loads_strict(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise ValueError("brief.json must be a JSON object")
    return data


def _file_digest(path: Path) -> str:
    raw = path.read_bytes()
    if _is_text(raw):
        raw = raw.replace(b"\r\n", b"\n")
    return hashlib.sha256(raw).hexdigest()


def manifest(brief_dir: Path, _found: Scan | None = None) -> dict[str, str]:
    """NFC POSIX relative path -> SHA-256 for every packaged file, sorted by path.

    Links are skipped here (``validate_layout`` rejects them and :func:`verify_hash`
    fails on them, so a skipped link can never hide content in an accepted package).
    Text (by content, see ``_is_text``) is hashed after CRLF->LF; everything else
    byte-exact. Raises ``PathCollision`` when two files collapse to one NFC path or
    differ only by case, ``PackageUnreadable`` when a directory could not be read (a
    silently skipped directory would hash as if it were empty), and ``ValueError``
    when ``brief.json`` is not a JSON object.
    """
    found = _found or scan_package(brief_dir)
    if found.errors:
        raise PackageUnreadable("; ".join(found.errors))
    out: dict[str, str] = {}
    seen: set[str] = set()
    for key, path in _package_files(found):
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


def verify_hash(brief_dir: Path, expected: str | None = None) -> tuple[bool, str]:
    """``(True, "")`` when the package hashes to ``expected`` (default: the
    ``package_sha256`` recorded in its ``brief.json``).

    Fails when the package holds a link or junction (its target is outside the
    hash), an unreadable directory, or excluded-but-present content. Trust anchor: the recorded hash lives INSIDE the package, so by default
    this detects an edit of the content or consent fields since the hash was
    recorded, not a rewrite of the whole directory (hash included). Callers that
    need that (approval) pass the ``expected`` hash they hold outside the package.
    """
    try:
        found = scan_package(brief_dir)
        if found.links:
            return False, "package contains links or junctions"
        if found.errors:
            return False, f"unreadable package: {'; '.join(found.errors)}"
        if unreported_exclusions(found):
            return False, "package contains excluded content (unhashed files a phase could read)"
        recorded = expected if expected is not None else _load_brief(found.root / "brief.json").get("package_sha256")
        actual = _digest(manifest(brief_dir, found))
    except (OSError, ValueError) as exc:  # UnicodeEncodeError is a ValueError
        return False, f"unreadable package: {exc}"
    if not isinstance(recorded, str) or not recorded:
        return False, "brief.json has no package_sha256"
    if recorded != actual:
        return False, f"package_sha256 mismatch (recorded {recorded[:12]}..., actual {actual[:12]}...)"
    return True, ""
