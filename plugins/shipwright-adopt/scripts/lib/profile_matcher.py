"""Match a detected stack signature against the available stack profiles.

Discovery runs over an ORDERED list of directories (project > user > bundled, D1):
the first directory that holds a name owns it, even when its file is invalid.
"""

from __future__ import annotations

import os
from typing import Any

try:  # tool context: lib/ is on sys.path (analyze_codebase._load_lib)
    from adopt_profile import load_resolver
except ImportError:  # test / package context: scripts/ on sys.path, lib is a package
    from lib.adopt_profile import load_resolver


def _flatten_profile_deps(profile: dict[str, Any]) -> set[str]:
    """Extract dependency-like identifiers from a profile's stack block."""
    names: set[str] = set()
    stack = profile.get("stack")
    if not isinstance(stack, dict):  # `stack` is untyped in the schema (D5): no deps, never a crash
        return names
    for group_name in ("runtime", "frontend", "backend"):
        group = stack.get(group_name, {})
        if isinstance(group, dict):
            for key in group.keys():
                names.add(key)
    auth = stack.get("auth")
    if isinstance(auth, dict) and "provider" in auth:
        names.add(str(auth["provider"]))
    elif isinstance(auth, str):
        names.add(auth)
    return names


def _flatten_signature_deps(signature: dict[str, Any]) -> set[str]:
    names: set[str] = set()
    for group_name in ("runtime", "frontend", "backend", "database", "auth"):
        group = signature.get(group_name, {})
        if isinstance(group, dict):
            for key in group.keys():
                names.add(key)
    return names


def _as_dirs(profile_dirs: Any) -> list[tuple[str, str]]:
    """``[(source, dir)]`` from an ordered list of dirs / ``(source, dir)`` pairs, or one dir."""
    if isinstance(profile_dirs, (str, os.PathLike)):
        profile_dirs = [profile_dirs]
    return [d if isinstance(d, tuple) else ("explicit", os.fspath(d)) for d in profile_dirs]


def _discover(dirs: list[tuple[str, str]]) -> tuple[list[dict[str, Any]], list[str]]:
    """Valid candidates (profile + provenance) and ``warnings[]`` for skipped ones.

    Ownership, validity, name rules, non-profile files and containment are the
    resolver's ``list_profiles`` (D1/D3): the first directory owns a name, valid or not.
    """
    _, pr = load_resolver()
    listing = pr.list_profiles(search_dirs=dirs)
    found: list[dict[str, Any]] = []
    # a missing user directory is the normal case, not a snapshot-worthy warning
    warnings: list[str] = [w for w in listing["warnings"] if not w.endswith("user profiles directory does not exist")]
    for row in listing["profiles"]:
        if not row["valid"]:
            warnings.append(f"{row['path']}: skipped, not a usable stack profile ({row['error']})")
            continue
        try:  # list_profiles validated the row; re-load for the data and the source classification
            res = pr.load_profile_file(row["path"], expected_name=row["name"], search_dirs=dirs)
        except ValueError as exc:  # file changed between listing and load
            warnings.append(f"{row['path']}: skipped, not a usable stack profile ({exc})")
            continue
        warnings.extend(res.warnings)
        found.append({"profile": res.data, "name": res.name, "source": res.source})
    return found, warnings


def match_profile(signature: dict[str, Any], profile_dirs: Any) -> dict[str, Any]:
    """Score each discovered profile against signature, return best match.

    ``profile_dirs`` is an ORDERED list of directories (or ``(source, dir)`` pairs);
    a single directory is accepted too. Scoring: Jaccard-like overlap over named
    dependencies, the same rule for bundled and custom profiles. Returns
        {"matched": <name>, "confidence": float [0.0..1.0], "candidates": [...],
         "source": project|user|bundled|explicit|builtin, "warnings": [...]}
    If nothing scores at least 0.30, returns ``generic`` (``source: builtin``)
    with confidence=0.0. An invalid candidate is skipped with a ``warnings`` entry.
    """
    sig_deps = _flatten_signature_deps(signature)
    candidates: list[dict[str, Any]] = []
    found, warnings = _discover(_as_dirs(profile_dirs))

    for item in found:
        profile_deps = _flatten_profile_deps(item["profile"])
        if not profile_deps:
            continue
        intersection = sig_deps & profile_deps
        union = sig_deps | profile_deps
        score = len(intersection) / len(union) if union else 0.0
        candidates.append({
            "name": item["name"],
            "score": round(score, 3),
            "matched_deps": sorted(intersection),
            "source": item["source"],
        })

    rank = {"project": 0, "user": 1, "explicit": 2, "bundled": 3}  # D1: a tie goes to the higher source
    candidates.sort(key=lambda c: (-c["score"], rank.get(c["source"], 9), c["name"]))
    if candidates and candidates[0]["score"] >= 0.30:
        return {
            "matched": candidates[0]["name"],
            "confidence": candidates[0]["score"],
            "candidates": candidates[:3],
            "source": candidates[0]["source"],
            "warnings": warnings,
        }
    return {"matched": "generic", "confidence": 0.0, "candidates": candidates[:3],
            "source": "builtin", "warnings": warnings}
