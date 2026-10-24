"""Brief package: layout validator and manifest hash (campaign brief-driven-run, D1).

A *Brief package* is the committed directory (default ``<project>/brief/``) an
operator hands ``/shipwright-run``: ``brief.json`` (v2), ``brief.md``,
``scope.md``, ``screen-map.json``, ``chat-map.json`` (chat-first only),
``mockups/``, ``visual-guidelines.md`` and optional ``inputs/``. ``evidence/`` is
never part of the package.

This module is the ONE implementation of two things; later units import it and
never re-implement them:

* :func:`validate_layout` -- structural defects, as a list (empty = accepted).
* :func:`package_sha256` -- a hash over a manifest (POSIX relative path -> SHA-256
  per file, NFC, sorted). Text files are hashed after CRLF->LF so an LF and a CRLF
  checkout hash the same. ``brief.json`` is hashed as canonical JSON WITHOUT
  ``package_sha256`` / ``approved_by`` / ``approved_at``, so every other field
  (``autonomy``, ``allow_parallel_builders``, ``deploy_target``...) is protected.

The hash proves the package is **unchanged since approval**, not that a person
approved it: any agent can recompute it.
"""

from __future__ import annotations

import hashlib
import json
import unicodedata
from pathlib import Path, PurePosixPath

BRIEF_VERSION = 2
#: Excluded from the hash and never read by a phase.
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


class PathCollision(ValueError):
    """Two packaged files collapse to the same NFC path."""


def _is_text(raw: bytes) -> bool:
    if 0 in raw[:_SNIFF_BYTES]:
        return False
    try:
        raw.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True


def _is_link(path: Path, root: Path) -> bool:
    """A symlink, or anything that resolves outside ``root`` (covers Windows junctions)."""
    if path.is_symlink():
        return True
    try:
        # Reached through a link/junction (inside or outside the package) when the
        # resolved path is not the plain root-relative path.
        return path.resolve() != root.resolve() / path.relative_to(root)
    except (OSError, ValueError):
        return True


def _is_junk(rel: PurePosixPath) -> bool:
    parts = [p.lower() for p in rel.parts]
    return (parts[-1] in JUNK_NAMES or parts[-1].startswith("._")
            or any(p in JUNK_DIRS for p in parts[:-1]))


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
    """POSIX-relative path (NFC) -> SHA-256 for every packaged file, sorted by path.

    Symlinks, ``evidence/`` and OS junk are skipped (``validate_layout`` rejects
    symlinks, so a skipped link can never hide content in an accepted package).
    Text (by content, see ``_is_text``) is hashed after CRLF->LF; everything else
    byte-exact. Raises ``ValueError`` when ``brief.json`` is not a JSON object (a
    package without a readable brief has no meaningful hash) or when two files
    collapse to one NFC path or differ only by case (one would silently drop out of
    the hash, or fail to check out on a case-insensitive filesystem).
    """
    root = Path(brief_dir)
    out: dict[str, str] = {}
    for path in root.rglob("*"):
        if _is_link(path, root) or not path.is_file():
            continue
        rel = PurePosixPath(*path.relative_to(root).parts)
        if rel.parts[0] in EXCLUDED_TOP_DIRS or _is_junk(rel):
            continue
        key = unicodedata.normalize("NFC", rel.as_posix())
        if key.casefold() in {k.casefold() for k in out}:
            raise PathCollision(f"two files collide on a case-insensitive filesystem: {key!r}")
        if key == "brief.json":
            brief = {k: v for k, v in _load_brief(path).items() if k not in HASH_EXCLUDED_BRIEF_KEYS}
            out[key] = hashlib.sha256(_canonical_json(brief)).hexdigest()
        else:
            out[key] = _file_digest(path)
    return dict(sorted(out.items()))


def package_sha256(brief_dir: Path) -> str:
    """One SHA-256 over the manifest of ``brief_dir``."""
    return hashlib.sha256(_canonical_json(manifest(brief_dir))).hexdigest()


def verify_hash(brief_dir: Path) -> tuple[bool, str]:
    """``(True, "")`` when ``brief.json``'s recorded ``package_sha256`` matches.

    Trust anchor: the recorded hash lives INSIDE the package, so this detects an
    edit of the content or consent fields since the hash was recorded, not a
    rewrite of the whole directory (hash included). Callers that need that
    (approval) compare against a hash they hold outside the package.
    """
    try:
        recorded = _load_brief(Path(brief_dir) / "brief.json").get("package_sha256")
        actual = package_sha256(brief_dir)
    except (OSError, ValueError) as exc:
        return False, f"unreadable package: {exc}"
    if not isinstance(recorded, str) or not recorded:
        return False, "brief.json has no package_sha256"
    if recorded != actual:
        return False, f"package_sha256 mismatch (recorded {recorded[:12]}..., actual {actual[:12]}...)"
    return True, ""


def _issue(code: str, path: str, message: str) -> dict[str, str]:
    return {"code": code, "path": path, "message": message}


def _bad_rel_path(value: object) -> bool:
    """True unless ``value`` is a non-empty, relative, forward-descending path."""
    if not isinstance(value, str) or not value.strip():
        return True
    norm = value.replace("\\", "/")
    drive = len(norm) > 1 and norm[1] == ":" and norm[0].isalpha()
    return norm.startswith("/") or drive or ".." in PurePosixPath(norm).parts


def _check_brief(brief: dict, root: Path, issues: list[dict[str, str]]) -> None:
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
        if isinstance(ref, str) and ref.strip() and (_bad_rel_path(ref) or not (root / ref).is_file()):
            issues.append(_issue("dangling_ref", "brief.json", f"{key} must name a file inside the package"))
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


def _read_text(f: Path, name: str, issues: list[dict[str, str]]) -> str | None:
    try:
        return f.read_text(encoding="utf-8-sig")
    except (UnicodeDecodeError, OSError) as exc:
        issues.append(_issue("bad_encoding", name, f"not readable as UTF-8 text: {exc}"))
        return None


def _safe_manifest_keys(root: Path) -> list[str]:
    try:
        return list(manifest(root))
    except (OSError, ValueError):
        return [p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()]


def validate_layout(brief_dir: Path) -> list[dict[str, str]]:
    """Structural defects of the package at ``brief_dir`` (empty list = accepted).

    Each defect is ``{"code", "path", "message"}``; the function reports, it does
    not raise. Required ``brief.json`` fields: ``REQUIRED_BRIEF_KEYS`` (D1's v2 set
    except the consent/approval trio, which the hash and preflight own).
    Hash freshness is a separate question -- see :func:`verify_hash`.
    """
    root = Path(brief_dir)
    if not root.is_dir():
        return [_issue("missing_dir", str(brief_dir), "brief directory does not exist")]
    issues: list[dict[str, str]] = []
    for path in root.rglob("*"):
        if _is_link(path, root):
            issues.append(_issue("symlink", path.relative_to(root).as_posix(),
                                 "links and junctions are not allowed"))
    try:
        manifest(root)
    except PathCollision as exc:
        issues.append(_issue("path_collision", ".", str(exc)))
    except OSError as exc:
        issues.append(_issue("unreadable_file", ".", f"a packaged file cannot be read: {exc}"))
    except ValueError:
        pass  # an unreadable brief.json is reported by the per-file checks below
    brief: dict | None = None
    for name in REQUIRED_FILES:
        f = root / name
        if not f.is_file() or _is_link(f, root):
            issues.append(_issue("missing_file", name, f"required file '{name}' is absent"))
            continue
        text = _read_text(f, name, issues)
        if text is None:
            continue
        if not text.strip():
            issues.append(_issue("empty_file", name, f"'{name}' is empty"))
        elif f.suffix == ".json":
            try:
                data = json.loads(text)
            except ValueError as exc:
                issues.append(_issue("invalid_json", name, f"not valid JSON: {exc}"))
                continue
            if name == "brief.json":
                if isinstance(data, dict):
                    brief = data
                else:
                    issues.append(_issue("invalid_json", name, "brief.json must be a JSON object"))
            elif name == "screen-map.json":
                _check_screen_map(root, data, issues)
    if not any(k.startswith("mockups/") for k in _safe_manifest_keys(root)):
        issues.append(_issue("missing_dir", "mockups", "mockups/ must hold at least one packaged file"))
    if brief is not None:
        _check_brief(brief, root, issues)
        if brief.get("ux_shape") == "chat-first" and not (root / "chat-map.json").is_file():
            issues.append(_issue("missing_file", "chat-map.json", "chat-first packages need chat-map.json"))
        if brief.get("ux_shape") == "classic" and (root / "chat-map.json").exists():
            issues.append(_issue("unexpected_file", "chat-map.json", "chat-map.json is chat-first only"))
    return issues


def _check_screen_map(root: Path, data: object, issues: list[dict[str, str]]) -> None:
    screens = data.get("screens") if isinstance(data, dict) else None
    if not isinstance(screens, list) or not screens:
        issues.append(_issue("bad_screen_map", "screen-map.json", "needs a non-empty 'screens' list"))
        return
    for entry in screens:
        mock = entry.get("mockup") if isinstance(entry, dict) else None
        if _bad_rel_path(mock) or not (root / "mockups" / mock).is_file() \
                or _is_link(root / "mockups" / mock, root):
            issues.append(_issue("dangling_mockup", "screen-map.json",
                                 f"screen entry references a missing or out-of-package mockup {mock!r}"))
