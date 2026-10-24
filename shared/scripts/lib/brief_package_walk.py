"""Brief package walk: which files belong to a package (campaign brief-driven-run, D1).

Implementation half of :mod:`lib.brief_package` (the one public import surface); split
out to keep each file small. One :func:`scan_package` walk yields the plain files, the
links/junctions (never entered) and the read errors; everything else works from that.
Junk DIRECTORIES (``__MACOSX/``, ``.git/``) are walked so their contents can be refused;
empty directories are neither hashed nor reported.
"""

from __future__ import annotations

import os
import unicodedata
from collections.abc import Iterator
from pathlib import Path, PurePosixPath
from typing import NamedTuple

#: Excluded from the hash. NOT a guarantee that no phase reads it: that holds only because
#: the snapshot copy omits ``evidence/``, which whoever builds the snapshot (B2/U3) owns. Only the exact-case top-level
#: ``evidence/`` DIRECTORY is skipped silently (and not walked); any other spelling,
#: or a FILE called ``evidence``, is reported as excluded content.
EXCLUDED_TOP_DIRS = frozenset({"evidence"})
#: Operating-system litter that must not change the hash.
JUNK_NAMES = frozenset({".ds_store", "thumbs.db", "desktop.ini", ".gitkeep"})
JUNK_DIRS = frozenset({"__macosx", ".git"})


class PackageUnreadable(OSError):
    """A directory or file of the package could not be read."""


class Scan(NamedTuple):
    """One walk of a package: the resolved root, plain files, links, read errors."""

    root: Path
    files: list[Path]
    links: list[str]
    errors: list[str]


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
            plain.remove("evidence")  # not walked, not hashed (the snapshot builder must omit it)
        dirnames[:] = plain
        for name in filenames:
            if _is_link(here / name, root):
                links.append((here / name).relative_to(root).as_posix())
            else:
                files.append(here / name)
    return Scan(root, files, links, errors)


def _quiet_exclusion(rel: PurePosixPath, path: Path) -> bool:
    """The ONLY excluded file tolerated silently: an exact-case, EMPTY ``.gitkeep``.

    Every other excluded file (``.DS_Store``, ``Thumbs.db``, ``desktop.ini``, ``._*``,
    anything under ``__MACOSX/`` or ``.git/``, a wrong-case ``Evidence/``) is REFUSED, not
    tolerated: no content sniff can prove a file harmless (a magic prefix is trivially
    spoofed), so the operator deletes it. Excluded files are never hashed and never
    yielded to a snapshot copy."""
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


def package_files(found: Scan) -> Iterator[tuple[str, Path]]:
    """``(NFC POSIX relative path, path)`` for every file of ``found`` that is hashed."""
    for path in found.files:
        rel = PurePosixPath(*path.relative_to(found.root).parts)
        if not _excluded(rel):
            yield unicodedata.normalize("NFC", rel.as_posix()), path


def iter_package_files(brief_dir: Path) -> Iterator[tuple[str, Path]]:
    """Yield ``(NFC POSIX relative path, path)`` for every file that belongs to the package.

    Raises ``PackageUnreadable`` when a directory could not be read (a skipped directory
    would silently shorten the package)."""
    found = scan_package(brief_dir)
    if found.errors:
        raise PackageUnreadable("; ".join(found.errors))
    yield from package_files(found)
