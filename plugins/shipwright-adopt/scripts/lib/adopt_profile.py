"""Adopt-side glue for the stack-profile resolver (campaign stack-profile-resolver, S3).

Adopt never looks a profile file up itself: discovery (the matcher) and selection
(the effective profile of ``generate_adoption_artifacts``) both go through the
resolver in ``shared/scripts`` (D1/D2). This module only holds what is adopt
specific: where to search, and the "resolve before any write" step.

The resolver lives in ``shared/scripts`` (a top-level module name, ADR-044/045):
APPEND that directory to ``sys.path`` for the import and remove it again, because
``shared/scripts`` holds a ``tools`` package that would shadow adopt's own.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# parents[0]=lib [1]=scripts [2]=shipwright-adopt [3]=plugins [4]=<repo root>.
_SHARED_SCRIPTS = str(Path(__file__).resolve().parents[4] / "shared" / "scripts")

SNAPSHOT_ORIGIN = ".shipwright/adopt/snapshot.json"


def load_resolver():
    """``(profile_consumer, profile_resolver)``; ImportError names the missing tree."""
    if not os.path.isfile(os.path.join(_SHARED_SCRIPTS, "profile_resolver.py")):
        raise ImportError(
            f"stack-profile resolver not found in {_SHARED_SCRIPTS} - the shipwright "
            "`shared/` tree must sit alongside the adopt plugin"
        )
    added = _SHARED_SCRIPTS not in sys.path
    if added:
        sys.path.append(_SHARED_SCRIPTS)
    try:
        import profile_consumer
        import profile_resolver
    finally:
        if added and _SHARED_SCRIPTS in sys.path:
            sys.path.remove(_SHARED_SCRIPTS)
    return profile_consumer, profile_resolver


class BundledProfilesMissing(FileNotFoundError):
    """The bundled stack-profiles directory is absent (incomplete install)."""


def hint_warning(project_root: Path, hint: str) -> str | None:
    """Why a ``--profile-hint`` would fail at generation time (it is resolved quietly), else None."""
    pc, _ = load_resolver()
    try:
        pc.resolve_named(hint, project_root, origin="--profile-hint", quiet=True)
    except ValueError as exc:
        return f"--profile-hint {hint!r} does not resolve: {exc}"
    return None


def discovery_dirs(project_root: Path) -> list:
    """The D1 triple ``[(source, dir)]`` for the matcher; a missing BUNDLED dir is an error.

    Project and user directories are routinely absent, so they are not checked here.
    The bundled directory is part of the install: without it every project would
    silently come out as ``generic`` (the old behaviour this replaces).
    """
    _, pr = load_resolver()
    dirs = pr.search_dirs(project_root)
    bundled = next((d for s, d in dirs if s == "bundled"), None)
    if not bundled or not os.path.isdir(bundled) or not os.path.isfile(pr.schema_path()):
        raise BundledProfilesMissing(
            f"bundled stack profiles directory or schema not found: {bundled or '(no bundled source)'} "
            "(the shipwright `shared/` tree is incomplete)"
        )
    return dirs


def resolve_effective(project_root: Path, override: str | None, snapshot: dict):
    """Resolve + validate the EFFECTIVE profile: the override, else the snapshot's match.

    Raises ``ValueError`` (``.kind`` / ``.exit_code``) with a remediation hint; the
    caller runs this before its first write. A reserved sentinel resolves to
    ``source: builtin`` without reading a file.
    """
    pc, pr = load_resolver()
    snapshot = snapshot if isinstance(snapshot, dict) else {}
    snap_profile = snapshot.get("profile")
    snap_profile = snap_profile if isinstance(snap_profile, dict) else {}
    matched = snap_profile.get("matched")
    if not override and not (isinstance(matched, str) and matched):
        raise ValueError(  # an unreadable/partial snapshot must not silently become `generic`
            f"{SNAPSHOT_ORIGIN} is unreadable or has no `profile.matched`; "
            "re-run analyze_codebase.py or pass --profile")
    name = override or matched
    if name == "detecting":  # the project phase's "not chosen yet" marker; adopt writes a real profile or generic
        raise ValueError("profile 'detecting' is only valid before a profile is chosen; use generic or a named profile")
    origin = "--profile" if override else SNAPSHOT_ORIGIN
    seen = snap_profile.get("source")
    try:
        res = pc.resolve_named(name, project_root, origin=origin)
    except ValueError as exc:
        if override or seen not in ("project", "user") or getattr(exc, "kind", "") != "not_found":
            raise
        raise pr.ProfileNotFound(  # the likely drift case: the file matched at analysis is gone
            f"profile {name!r} was matched from the {seen} profiles at analysis time but no longer "
            "exists. Re-run analyze_codebase.py, or pass --profile."
        ) from exc
    # Provenance recorded at analysis must still hold: a project profile deleted (or a user
    # file added) since then would silently swap in another file and its templates (D9).
    if not override and seen in ("project", "user", "bundled") and res.source != seen:
        raise pr.ProfileInvalid(
            f"profile {name!r} was matched from the {seen} profiles at analysis time but now "
            f"resolves from {res.source} ({res.path}). Re-run analyze_codebase.py, or pass --profile."
        )
    return res
