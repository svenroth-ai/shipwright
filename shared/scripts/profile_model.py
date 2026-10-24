"""Types, constants, name rules and D5 validation for stack profiles.

Split out of ``profile_resolver`` (300-line source limit). The D2 hot-file rule
(only S1 edits the resolver) covers ``profile_resolver.py``, ``profile_model.py`` and
``profile_schema_check.py`` together. Consumers import
from ``profile_resolver``, which re-exports everything public here.
"""

from __future__ import annotations

import difflib
import functools
import json
import os
import re
import sys
from dataclasses import dataclass, field

_HERE = os.path.dirname(os.path.abspath(__file__))
_ADDED = _HERE not in sys.path
if _ADDED:
    sys.path.append(_HERE)
import profile_schema_check as _psc  # noqa: E402

if _ADDED:  # leave sys.path as found (shared/scripts holds a `tools` package)
    sys.path.remove(_HERE)

SCHEMA_VERSION_SUPPORTED = 1
CONTRACT_VERSION = 1
USER_DIR_ENV = "SHIPWRIGHT_USER_PROFILES_DIR"
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
SENTINELS = ("generic", "detecting")
_DEVICE_NAMES = frozenset(
    {"con", "prn", "aux", "nul"}
    | {f"com{i}" for i in range(1, 10)}
    | {f"lpt{i}" for i in range(1, 10)}
)
# Files in shared/profiles that are NOT stack profiles (never listed/resolved).
NON_PROFILE_FILES = (
    "reducibility-idioms.json",
    "deploy-profile.schema.json",
    "deploy-profile-schema.md",
)
_NON_PROFILE_STEMS = frozenset(f[:-5] for f in NON_PROFILE_FILES if f.endswith(".json"))


def is_non_profile(name: str) -> bool:
    return name in _NON_PROFILE_STEMS


class ProfileError(ValueError):
    kind = "error"
    exit_code = 1


class ProfileNotFound(ProfileError):
    kind = "not_found"
    exit_code = 2


class ProfileInvalid(ProfileError):
    kind = "invalid"
    exit_code = 3


class ProfileSchemaDrift(ProfileError):
    kind = "schema_drift"
    exit_code = 3


class ProfileSchemaUnsupported(ProfileError):
    kind = "schema_unsupported"
    exit_code = 3


@dataclass
class ResolvedProfile:
    name: str
    source: str  # project | user | bundled | builtin | explicit
    path: str | None
    data: dict
    schema_version: int = SCHEMA_VERSION_SUPPORTED
    shadows: list = field(default_factory=list)
    shadows_bundled: bool = False
    warnings: list = field(default_factory=list)
    searched: list = field(default_factory=list)

    @property
    def custom(self) -> bool:
        """True unless bundled/builtin: gates every bundled-only default (D9)."""
        return self.source not in ("bundled", "builtin")

    def to_dict(self, include_data: bool = False) -> dict:
        out = {
            "name": self.name, "source": self.source, "path": self.path,
            "schema_version": self.schema_version, "shadows": list(self.shadows),
            "warnings": list(self.warnings), "searched": list(self.searched),
        }
        if include_data:
            out["data"] = self.data
        return out


def bundled_dir() -> str:
    return os.path.normpath(os.path.join(_HERE, "..", "profiles"))


def schema_path() -> str:
    return os.path.normpath(os.path.join(_HERE, "..", "schemas", "stack_profile.schema.json"))


def user_dir() -> str | None:
    env = os.environ.get(USER_DIR_ENV)
    if env:
        # A relative value would resolve against the cwd (repo-controlled, differs per worktree).
        return env if os.path.isabs(env) else None
    home = os.path.expanduser("~")
    if not home or home.startswith("~"):
        return None  # home cannot be determined: no user source
    return os.path.join(home, ".shipwright", "profiles")


def search_dirs(project_root: str | os.PathLike | None) -> list:
    """The D1 triple as ``[(source, dir)]`` (user entry omitted without a home)."""
    dirs = []
    if project_root is not None:
        dirs.append(("project", os.path.join(os.path.abspath(os.fspath(project_root)), ".shipwright", "profiles")))
    u = user_dir()
    if u:
        dirs.append(("user", u))
    dirs.append(("bundled", bundled_dir()))
    return dirs


def path_within(child: str, parent: str, flavour=None) -> bool:
    """True when ``child`` is ``parent`` or below it, by pure string semantics of a path
    flavour (``ntpath`` / ``posixpath``; default: this OS). Windows rules: drive letters,
    UNC shares and case-insensitivity. Callers pass already-resolved paths."""
    mod = flavour or os.path
    c, p = mod.normcase(mod.normpath(child)), mod.normcase(mod.normpath(parent))
    try:
        return mod.commonpath([c, p]) == p
    except ValueError:  # different drives, or an absolute path mixed with a relative one
        return False


def check_name(name: object) -> str:
    """D3 name rules for NAME lookups; raises ProfileInvalid."""
    if not isinstance(name, str) or not name:
        raise ProfileInvalid(f"Invalid profile name {name!r}: must be a non-empty string")
    low = name.lower()
    if low in SENTINELS or low in _DEVICE_NAMES:
        raise ProfileInvalid(f"Invalid profile name {name!r}: reserved name")
    if not NAME_RE.fullmatch(name):
        raise ProfileInvalid(
            f"Invalid profile name {name!r}: use lowercase letters, digits and '-' only "
            "(pattern ^[a-z0-9][a-z0-9-]*$); no paths, no dots, no upper case"
        )
    return name


def bundled_names() -> list:
    try:
        entries = os.listdir(bundled_dir())
    except OSError:
        return []
    return sorted(
        e[:-5] for e in entries if e.endswith(".json") and e not in NON_PROFILE_FILES
    )


def _drift(path: str, what: str, name: str) -> ProfileSchemaDrift:
    close = difflib.get_close_matches(name, bundled_names(), 1) or bundled_names()[:1]
    start = f"copy the bundled profile `{close[0]}` as a new starting point" if close else "start from a bundled profile"
    return ProfileSchemaDrift(
        f"Profile file {path}: {what}. This Shipwright supports stack-profile "
        f"schema_version {SCHEMA_VERSION_SUPPORTED}; {start}."
    )


@functools.lru_cache(maxsize=4)
def _load_schema(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as fh:
            schema = json.load(fh)
        _psc.assert_supported(schema)
    except (OSError, ValueError) as exc:  # missing / corrupt / unsupported schema
        raise ProfileSchemaUnsupported(f"stack-profile schema {path} is unusable: {exc}") from exc
    return schema


def _schema() -> dict:
    return _load_schema(schema_path())


def validate_profile_data(data: object, path: str) -> int:
    """D5 validation; returns the effective schema_version or raises."""
    if not isinstance(data, dict):
        raise ProfileInvalid(f"Profile file {path}: top level must be a JSON object")
    name = data.get("name") if isinstance(data.get("name"), str) else os.path.basename(path)[:-5]
    sv = data.get("schema_version", SCHEMA_VERSION_SUPPORTED)
    if isinstance(sv, bool) or not (isinstance(sv, int) or (isinstance(sv, float) and sv.is_integer())):
        raise _drift(path, "schema_version must be an integer", name)
    sv = int(sv)
    if sv < 1 or sv > SCHEMA_VERSION_SUPPORTED:
        raise _drift(path, f"unsupported schema_version {sv}", name)
    for code, msg in _psc.check(data, _schema(), "$"):
        if code == "required":
            raise ProfileInvalid(f"Profile file {path}: {msg}")
        raise _drift(path, msg, name)
    return sv


def provenance_lines(res: ResolvedProfile) -> list:
    """Stderr lines every command-running resolution must emit (D8a/b)."""
    where = res.path or "built-in defaults"
    lines = [f"profile {res.name!r}: source={res.source} ({where})"]
    lines += [f"shadows: {p}" for p in res.shadows]
    lines += res.warnings
    return lines
