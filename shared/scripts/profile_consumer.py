"""Loader-side glue for stack-profile resolution (campaign stack-profile-resolver, S2).

Every Python loader that reads a stack profile (dev_server, validate_env,
test_runner, performance_check, setup-design-session) goes through here, so the
"no silent fallback" rules, the remediation text and the provenance lines exist
once. The resolver (``profile_resolver``) stays the only place that looks files up.

Import convention (D2): APPEND ``shared/scripts`` to ``sys.path``, import, and
remove the entry again if this import added it (``shared/scripts`` holds a
``tools`` package that would shadow a plugin's own)::

    import profile_consumer as pc

Errors are the resolver's: ``ValueError`` subclasses carrying ``.kind`` /
``.exit_code``. Callers catch ``ValueError`` and branch on ``.kind``; they never
name the classes.
"""

from __future__ import annotations

import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ADDED = _HERE not in sys.path
if _ADDED:
    sys.path.append(_HERE)
import profile_resolver as pr  # noqa: E402
from profile_resolver import ProfileInvalid  # noqa: E402,F401

if _ADDED:
    sys.path.remove(_HERE)

RUN_CONFIG = "shipwright_run_config.json"
SENTINELS = pr.SENTINELS


def _hint(exc: ValueError, origin: str | None) -> str:
    where = origin or "the profile name you passed"
    if getattr(exc, "kind", "") == "not_found":
        if origin and origin.startswith("--"):
            return (f"The name comes from the {origin} option: fix the {origin} value (or `profile` in "
                    f"{RUN_CONFIG}), add the profile file, or set it to generic.")
        cfg = origin if origin and origin.endswith(".json") else RUN_CONFIG
        return (f"The profile name comes from {where}: fix `profile` in {cfg}, "
                "add the profile file, or set it to generic.")
    return (f"Fix the profile file named above, or change the profile (from {where}) "
            "to another profile or generic.")


def with_hint(exc: ValueError, origin: str | None) -> ValueError:
    """Same exception class, message extended with the remediation text."""
    try:
        return type(exc)(f"{exc}\n{_hint(exc, origin)}")
    except TypeError:
        return exc


def name_over_bundled_path(profile, profile_path):
    """``(profile, path, name_from_path)``: a ``--profile-path`` that only spells a bundled file becomes its NAME.

    Skill prose (until S4) passes ``--profile-path <shared>/profiles/X.json``, with or without
    ``--profile X``. Taking that path literally would skip project/user profiles and break
    sentinels (no ``generic.json``); the NAME is what the caller meant (D8f), so resolve by name.
    Both sides are compared as real paths (the prose path is ``<plugin>/../../shared`` and may cross
    a symlink, junction or ``..``). A path to a different bundled file than ``--profile`` names
    stays explicit; the bare ``<bundled>/.json`` (an empty ``{profile}``) names nothing.
    """
    if not profile_path:
        return profile, profile_path, False
    base = os.path.basename(str(profile_path))
    # no abspath: it would collapse `link/..` lexically before the symlink is followed
    here = os.path.normcase(os.path.join(os.path.realpath(os.path.dirname(os.fspath(profile_path)) or os.curdir), base))
    stem, ext = os.path.splitext(base)
    if here != os.path.normcase(os.path.join(os.path.realpath(pr.bundled_dir()), base)):
        return profile, profile_path, False
    if base == ".json":
        return profile, None, False
    if ext == ".json" and profile in (None, "", stem):
        return stem, None, not profile
    return profile, profile_path, False


def emit(res, stream=None, prefix: str = "[profile] ") -> None:
    """Provenance (source, shadows, shadow warning) on stderr (D8 a/b)."""
    out = stream or sys.stderr
    for line in pr.provenance_lines(res):
        out.write(f"{prefix}{line}\n")


def search_dirs_with_bundled(project_root, bundled: str) -> list:
    """The D1 triple with the bundled entry replaced (tests / dev_server keep their own seam)."""
    return [(s, bundled if s == "bundled" else d) for s, d in pr.search_dirs(project_root)]


def config_profile(project_root, filename: str = RUN_CONFIG) -> str | None:
    """The ``profile`` named in ``<project_root>/<filename>``.

    Absent file, absent key, null or empty -> ``None`` ("names nothing"). A file that
    is corrupt, not an object, or whose ``profile`` is not a string raises (never a
    silent default).
    """
    path = os.path.join(os.fspath(project_root), filename)
    try:
        with open(path, encoding="utf-8-sig") as fh:
            data = json.load(fh)
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as exc:
        raise ProfileInvalid(
            f"{path} cannot be read ({exc}). Fix the file, or remove `profile` from it."
        ) from exc
    if not isinstance(data, dict):
        raise ProfileInvalid(f"{path}: top level must be a JSON object. Fix the file.")
    name = data.get("profile")
    if name is None or name == "":
        return None
    if not isinstance(name, str):
        raise ProfileInvalid(
            f"{path}: `profile` must be a string (got {type(name).__name__}). "
            "Fix `profile`, add the profile file, or set it to generic."
        )
    return name


def resolve_named(name, project_root, *, origin: str | None = None, search_dirs=None,
                  stream=None, quiet: bool = False):
    """``resolve_profile`` + remediation text + provenance lines on stderr."""
    try:
        res = pr.resolve_profile(name, project_root, search_dirs=search_dirs)
    except ValueError as exc:
        raise with_hint(exc, origin) from exc
    if not quiet:
        emit(res, stream)
    return res


def load_explicit(path, project_root=None, *, expected_name=None, stream=None, quiet: bool = False):
    """``load_profile_file`` (explicit ``--profile-path`` / ``--profile-dir`` file) + provenance."""
    res = pr.load_profile_file(path, expected_name, project_root=project_root)
    if not quiet:
        emit(res, stream)
    return res


def resolve_in_dir(name, directory, project_root=None, *, origin: str | None = None, quiet: bool = False):
    """Look ``name`` up in ONE explicit directory (``--profile-dir``).

    The NAME gets the D3 rules (it is a name lookup); the file is read through
    ``load_profile_file`` (D5, ``source: explicit`` unless it lies in a searched dir).
    A missing file is "not found" - never a fall-through to another source.
    """
    if name in SENTINELS:
        return resolve_named(name, project_root, origin=origin,
                             search_dirs=[("explicit", os.fspath(directory))], quiet=quiet)
    try:
        pr.check_name(name)
        path = os.path.join(os.fspath(directory), f"{name}.json")
        if not os.path.isfile(path):
            raise pr.ProfileNotFound(
                f"Stack profile {name!r} not found. Searched:\n  - {os.fspath(directory)}")
        return load_explicit(path, project_root, expected_name=name, quiet=quiet)
    except ValueError as exc:
        raise with_hint(exc, origin) from exc


def error_fields(exc: ValueError) -> dict:
    return {"error": str(exc), "kind": getattr(exc, "kind", "error")}


def exit_code(exc: ValueError) -> int:
    return getattr(exc, "exit_code", 1)
