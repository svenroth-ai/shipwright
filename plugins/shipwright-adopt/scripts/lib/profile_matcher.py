"""Match a detected stack signature against available shared/profiles/*.json."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _flatten_profile_deps(profile: dict[str, Any]) -> set[str]:
    """Extract dependency-like identifiers from a profile's stack block."""
    names: set[str] = set()
    stack = profile.get("stack", {})
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


def match_profile(signature: dict[str, Any], profiles_dir: Path) -> dict[str, Any]:
    """Score each profile against signature, return best match.

    Scoring: Jaccard-like overlap over named dependencies. Returns
        {"matched": <name>, "confidence": float [0.0..1.0], "candidates": [...]}
    If nothing scores above 0.30, returns ``generic`` with confidence=0.0.
    """
    sig_deps = _flatten_signature_deps(signature)
    candidates: list[dict[str, Any]] = []

    if not profiles_dir.is_dir():
        return {"matched": "generic", "confidence": 0.0, "candidates": []}

    for profile_file in sorted(profiles_dir.glob("*.json")):
        try:
            profile = json.loads(profile_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        profile_deps = _flatten_profile_deps(profile)
        if not profile_deps:
            continue
        intersection = sig_deps & profile_deps
        union = sig_deps | profile_deps
        score = len(intersection) / len(union) if union else 0.0
        candidates.append({
            "name": profile.get("name", profile_file.stem),
            "score": round(score, 3),
            "matched_deps": sorted(intersection),
        })

    candidates.sort(key=lambda c: c["score"], reverse=True)
    if candidates and candidates[0]["score"] >= 0.30:
        return {
            "matched": candidates[0]["name"],
            "confidence": candidates[0]["score"],
            "candidates": candidates[:3],
        }
    return {"matched": "generic", "confidence": 0.0, "candidates": candidates[:3]}
