"""Brief package hash: manifest, digest, verification (campaign brief-driven-run, D1).

Implementation half of :mod:`lib.brief_package` (the one public import surface).
Which files belong to the package lives in :mod:`lib.brief_package_walk`.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

from .brief_package_walk import PackageUnreadable, Scan, package_files, scan_package, unreported_exclusions

BRIEF_VERSION = 2
#: Consent/approval fields removed from ``brief.json`` before hashing.
HASH_EXCLUDED_BRIEF_KEYS = frozenset({"package_sha256", "approved_by", "approved_at"})
#: A file is text (CRLF->LF before hashing) when its first 8000 bytes hold no NUL byte --
#: git's own heuristic, so a checkout with ``core.autocrlf`` hashes the same as one without.
#: Content, not extension, decides (a ``.tsx`` or extensionless file normalises like a ``.md``).
#: Consequence: a NUL-free file whose line endings are changed by an edit that keeps its
#: meaning IS NOT protected -- ``\r\n`` and ``\n`` hash the same by design.
_SNIFF_BYTES = 8000


class PathCollision(ValueError):
    """Two packaged files collapse to one NFC path or differ only by case.

    Case-folding over-approximates (``ss`` vs ``ß`` also collide): it fails closed, so a
    package that cannot be checked out on every OS is refused rather than ambiguous."""


def _is_text(raw: bytes) -> bool:
    return 0 not in raw[:_SNIFF_BYTES]


def _canonical_json(obj: object) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _no_duplicate_keys(pairs: list[tuple[str, object]]) -> dict:
    out: dict = {}
    for key, value in pairs:
        if key in out:
            raise ValueError(f"duplicate JSON key {key!r}")
        out[key] = value
    return out


def _refuse_constant(name: str) -> object:
    raise ValueError(f"non-finite JSON number {name}")


def _finite_float(text: str) -> float:
    value = float(text)
    if not math.isfinite(value):
        raise ValueError(f"non-finite JSON number {text}")
    return value


def loads_strict(text: str) -> object:
    """``json.loads`` that refuses duplicate keys (a raw-text reader and a parser would
    disagree on them), ``NaN`` / ``Infinity`` / overflowing floats (not portable JSON),
    and turns absurd nesting into a ``ValueError``."""
    try:
        return json.loads(text, object_pairs_hook=_no_duplicate_keys,
                          parse_constant=_refuse_constant, parse_float=_finite_float)
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

    Links are skipped here (``validate_layout`` rejects them and the verifiers fail on
    them, so a skipped link can never hide content in an accepted package). Text (by
    content, see ``_is_text``) is hashed after CRLF->LF; everything else byte-exact.
    Raises ``PathCollision`` when two files collapse to one NFC path or differ only by
    case, ``PackageUnreadable`` when a directory could not be read (a silently skipped
    directory would hash as if it were empty), and ``ValueError`` when ``brief.json`` is
    not a JSON object.
    """
    found = _found or scan_package(brief_dir)
    if found.errors:
        raise PackageUnreadable("; ".join(found.errors))
    out: dict[str, str] = {}
    seen: set[str] = set()
    for key, path in package_files(found):
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


def check_hash(found: Scan, expected: str | None) -> tuple[bool, str]:
    """Compare the package of ``found`` to ``expected`` (default: the hash recorded in its
    ``brief.json``). Fails on links/junctions, unreadable directories and excluded-but-
    present content before it hashes anything."""
    try:
        if found.links:
            return False, "package contains links or junctions"
        if found.errors:
            return False, f"unreadable package: {'; '.join(found.errors)}"
        if unreported_exclusions(found):
            return False, "package contains excluded content (unhashed files a phase could read)"
        recorded = expected if expected is not None else \
            _load_brief(found.root / "brief.json").get("package_sha256")
        actual = _digest(manifest(found.root, found))
    except (OSError, ValueError) as exc:  # UnicodeEncodeError is a ValueError
        return False, f"unreadable package: {exc}"
    if not isinstance(recorded, str) or not recorded:
        return False, "brief.json has no package_sha256"
    if recorded != actual:
        return False, f"package_sha256 mismatch (recorded {recorded[:12]}..., actual {actual[:12]}...)"
    return True, ""


def verify_hash(brief_dir: Path, *, expected: str) -> tuple[bool, str]:
    """``(True, "")`` when the package hashes to ``expected`` -- a hash the CALLER holds
    OUTSIDE the package (run_config, an event). This is the only form that proves
    "unchanged since approval"; ``approved_by`` / ``approved_at`` are not hashed, so the
    approval itself must be anchored outside the package (B2/U3 obligation)."""
    return check_hash(scan_package(brief_dir), expected)


def verify_recorded_hash(brief_dir: Path) -> tuple[bool, str]:
    """Self-consistency only: the package matches the ``package_sha256`` written in its own
    ``brief.json``. TAMPER-EVIDENCE, NOT APPROVAL -- whoever edits the package can rewrite
    the recorded hash too, and ``approved_by`` / ``approved_at`` sit outside the hash."""
    return check_hash(scan_package(brief_dir), None)
