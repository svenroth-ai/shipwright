"""Stack-profile resolver: project > user > bundled, first FILE wins.

One implementation for every phase that reads a stack profile (campaign
stack-profile-resolver, decisions D1-D10). Stdlib-only; at module scope only
``os.path`` and constants (no ``Path.home()``, no platform-gated imports --
``dev_server`` pins this at import time).

Lookup order for a NAME (``<name>.json``): ``<project>/.shipwright/profiles``,
then the user directory (``SHIPWRIGHT_USER_PROFILES_DIR`` or
``~/.shipwright/profiles``), then the bundled ``shared/profiles``. The first
file found wins and resolution NEVER falls through: a winning file that is
unreadable, not JSON or invalid raises. ``generic`` / ``detecting`` are
reserved sentinels (``source: builtin``, no file read).

Import convention: APPEND ``shared/scripts`` to ``sys.path`` and
``from profile_resolver import ...``. Callers catch ``ValueError`` and branch
on ``.kind`` / ``.exit_code``; they never name the exception classes.

The D2 hot-file rule covers this module, ``profile_model.py`` and
``profile_schema_check.py`` together.

Resolution is read-only and runs no commands and no env expansion.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

_HERE = os.path.dirname(os.path.abspath(__file__))
_ADDED = _HERE not in sys.path
if _ADDED:
    sys.path.append(_HERE)
from profile_model import (  # noqa: E402,F401
    CONTRACT_VERSION, NAME_RE, NON_PROFILE_FILES, SCHEMA_VERSION_SUPPORTED,
    SENTINELS, USER_DIR_ENV, ProfileError, ProfileInvalid, ProfileNotFound,
    ProfileSchemaDrift, ProfileSchemaUnsupported, ResolvedProfile, is_non_profile,
    bundled_dir, bundled_names, check_name, provenance_lines, schema_path,
    search_dirs, user_dir, validate_profile_data,
)
if _ADDED:  # leave sys.path as found (shared/scripts holds a `tools` package)
    sys.path.remove(_HERE)

def _norm_dirs(project_root, dirs) -> list:
    if dirs is None:
        return search_dirs(project_root)
    return [d if isinstance(d, tuple) else ("explicit", os.fspath(d)) for d in dirs]


def _read_json(path: str):
    try:
        with open(path, encoding="utf-8-sig") as fh:
            return json.load(fh)
    except OSError as exc:
        raise ProfileInvalid(f"Profile file {path} is unreadable: {exc}") from exc
    except ValueError as exc:  # JSONDecodeError / UnicodeDecodeError
        raise ProfileInvalid(f"Profile file {path} is not valid JSON: {exc}") from exc
    except (RecursionError, MemoryError) as exc:  # hostile deep nesting must not break list
        raise ProfileInvalid(f"Profile file {path} is too deeply nested or too large to parse") from exc


def _inside(path: str, directory: str) -> bool:
    try:
        return Path(path).resolve().is_relative_to(Path(directory).resolve())
    except (OSError, ValueError, RuntimeError):  # RuntimeError: symlink loop on 3.11
        return False


def _load(path: str, source: str, expected_name: str | None, real: str | None = None) -> ResolvedProfile:
    real = real or os.path.realpath(path)
    data = _read_json(real)
    sv = validate_profile_data(data, path)
    if expected_name is not None and data.get("name") != expected_name:
        raise ProfileInvalid(
            f"Profile file {path}: name {data.get('name')!r} must equal the file name "
            f"{expected_name!r}"
        )
    return ResolvedProfile(data["name"], source, path, data, sv)


def _listdir(directory: str, strict: bool) -> list:
    """Entries of ``directory``; absent -> []. An existing-but-unreadable directory
    raises unless ``strict`` is False (user source), so a lower source can never
    silently win (D1)."""
    try:
        return os.listdir(directory)
    except FileNotFoundError:
        return []
    except OSError as exc:
        if strict:
            raise ProfileInvalid(f"Profile directory {directory} cannot be read: {exc}") from exc
        return []


def _entry(directory: str, name: str, strict: bool = True):
    """Exact directory-entry spelling check for the WINNING candidate; path or None."""
    want = name + ".json"
    hits = [e for e in _listdir(directory, strict) if e.lower() == want]
    if len(hits) > 1:
        raise ProfileInvalid(
            f"Profile files in {directory} differ only in case: {', '.join(sorted(hits))}"
        )
    if not hits:
        return None
    if hits[0] != want:
        raise ProfileInvalid(
            f"Profile file {os.path.join(directory, hits[0])}: file names must be lowercase "
            f"(expected {want!r}, so Windows, macOS and Linux behave the same)"
        )
    return os.path.join(directory, want)


def resolve_profile(name: str, project_root=None, *, search_dirs=None) -> ResolvedProfile:
    """Resolve a profile NAME. ``search_dirs`` overrides the D1 triple."""
    searched = _norm_dirs(project_root, search_dirs)
    if isinstance(name, str) and name in SENTINELS:
        for source, directory in searched:  # a <sentinel>.json is an error in any source (D3)
            clash = [e for e in _listdir(directory, strict=source != "user")
                     if e.lower() == name + ".json"]
            if clash:
                raise ProfileInvalid(
                    f"Profile file {os.path.join(directory, clash[0])}: {name!r} is a reserved "
                    "built-in name and cannot be redefined by a file; rename it"
                )
        return ResolvedProfile(name, "builtin", None, {}, searched=[d for _, d in searched])
    check_name(name)
    if is_non_profile(name):
        raise ProfileNotFound(f"{name!r} is not a stack profile")
    winner = None
    shadows: list = []
    shadows_bundled = False
    seen: set = set()
    for source, directory in searched:
        real_dir = os.path.realpath(directory)
        if real_dir in seen:
            continue
        seen.add(real_dir)
        if winner is not None:  # lower source: record as a shadow, never validate it
            low = [e for e in _listdir(directory, False) if e.lower() == name + ".json"]
            if low:
                shadows.append(os.path.join(directory, low[0]))
                shadows_bundled = shadows_bundled or source == "bundled"
            continue
        path = _entry(directory, name, strict=source != "user")
        if path is None:
            continue
        try:
            real = Path(path).resolve()  # resolved ONCE; this exact path is what gets read
            contained = real.is_relative_to(Path(directory).resolve())
        except (OSError, RuntimeError) as exc:  # RuntimeError: symlink loop on 3.11
            raise ProfileInvalid(f"Profile file {path} cannot be resolved: {exc}") from exc
        if not contained:
            raise ProfileInvalid(f"Profile file {path} resolves outside {directory}")
        winner = _load(path, source, name, str(real))
    if winner is None:
        listing = "\n".join(f"  - {d}" for _, d in searched)
        raise ProfileNotFound(
            f"Stack profile {name!r} not found. Searched:\n{listing}\n"
            f"Add {name}.json to one of these, or use a bundled profile "
            f"({', '.join(bundled_names())}) or 'generic'."
        )
    winner.shadows, winner.shadows_bundled = shadows, shadows_bundled
    winner.searched = [d for _, d in searched]
    if winner.custom and shadows_bundled:
        winner.warnings.append(
            f"WARNING: {winner.source} profile {winner.path} shadows the bundled "
            f"profile {name!r}; ITS commands run instead of the bundled ones."
        )
    return winner


def load_profile_file(path, expected_name: str | None = None, *, project_root=None, search_dirs=None) -> ResolvedProfile:
    """Parse + D5-validate an explicit file; D3 name rules do not apply.

    The path is classified against the search dirs: inside a source dir ->
    that source (and its ``shadows``); otherwise ``source: explicit`` (custom).
    """
    path = os.fspath(path)
    dirs = _norm_dirs(project_root, search_dirs)
    source, idx = "explicit", -1  # an explicit file outranks every searched dir
    for i, (src, directory) in enumerate(dirs):
        if os.path.isdir(directory) and _inside(path, directory):
            source, idx = src, i
            break
    res = _load(path, source, expected_name)
    res.searched = [d for _, d in dirs]
    stem = os.path.splitext(os.path.basename(path))[0].lower() or res.name
    real = os.path.realpath(path)
    for i, (src, directory) in enumerate(dirs):
        other = os.path.join(directory, stem + ".json")
        if i > idx and os.path.isfile(other) and os.path.realpath(other) != real:
            res.shadows.append(other)
            res.shadows_bundled = res.shadows_bundled or src == "bundled"
    if res.custom and res.shadows_bundled:
        res.warnings.append(
            f"WARNING: {res.source} profile {res.path} shadows the bundled profile "
            f"{res.name!r}; ITS commands run instead of the bundled ones."
        )
    return res


def list_profiles(project_root=None, *, search_dirs=None) -> dict:
    """Discovery (not selection): invalid candidates are listed ``valid: false``."""
    dirs = _norm_dirs(project_root, search_dirs)
    owners: dict = {}
    warnings: list = []
    seen: set = set()
    for source, directory in dirs:
        if os.path.realpath(directory) in seen:  # same directory twice: never its own shadow
            continue
        seen.add(os.path.realpath(directory))
        if not os.path.exists(directory):
            if source == "user":  # D4: a missing user dir is absent for resolve, a warning in list
                warnings.append(f"{directory}: user profiles directory does not exist")
            continue
        try:
            entries = sorted(os.listdir(directory))
        except OSError as exc:
            warnings.append(f"{directory}: cannot list profiles ({exc.strerror or exc})")
            continue
        names = [e for e in entries if e.lower().endswith(".json") and e not in NON_PROFILE_FILES]
        groups: dict = {}
        for e in names:
            groups.setdefault(e[:-5].lower(), []).append(e)
        for key, files in groups.items():
            if key in owners:
                owners[key]["shadows"].extend(os.path.join(directory, f) for f in files)
                continue
            row = _row(source, directory, files)
            owners[key] = row
    rows = sorted(owners.values(), key=lambda r: r["name"])
    return {
        "contract_version": CONTRACT_VERSION,
        "profiles": rows,
        "warnings": warnings,
        "searched": [d for _, d in dirs],
    }


def _row(source: str, directory: str, files: list) -> dict:
    stem = files[0][:-5]
    path = os.path.join(directory, files[0])
    row = {"name": stem, "source": source, "path": path, "valid": True,
           "error": None, "kind": None, "schema_version": None,
           "description": None, "shadows": []}
    try:
        if len(files) > 1:
            raise ProfileInvalid(
                f"Profile files in {directory} differ only in case: {', '.join(files)}"
            )
        if files[0] != stem.lower() + ".json":
            raise ProfileInvalid(f"Profile file {path}: file names must be lowercase")
        check_name(stem)
        if not _inside(path, directory):
            raise ProfileInvalid(f"Profile file {path} resolves outside {directory}")
        res = _load(path, source, stem)
        row["schema_version"] = res.schema_version
        desc = res.data.get("description")
        row["description"] = desc if isinstance(desc, str) else None
    except ProfileError as exc:
        row.update(valid=False, error=str(exc), kind=exc.kind)
    return row
