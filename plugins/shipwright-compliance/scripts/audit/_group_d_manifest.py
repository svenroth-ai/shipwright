"""Manifest load + fail-closed read-validation + collision analysis for the Group-D
traceability detectives (TT2 hardening — coordinator MUST-FIX 2/3).

Kept separate from ``_group_d_traceability`` so both stay under the 300-LOC cap. Every
function here is fail-CLOSED: a manifest that cannot be trusted yields ``None`` (→ SKIP,
never a silent pass), and the collision analysis counts an id as ambiguous the moment it
is shared across namespaces (including a ``removed`` occurrence).
"""

from __future__ import annotations

import json
from pathlib import Path

_MANIFEST_REL = ".shipwright/compliance/test-traceability.json"
_SCHEMA_PATH = Path(__file__).resolve().parents[1] / "lib" / "traceability_schema.json"


def _schema_valid(data: dict) -> bool:
    """Validate ``data`` against ``traceability_schema.json`` (MUST-FIX 3).

    Fail-CLOSED: if jsonschema is unavailable or the schema is unreadable, we CANNOT
    confirm the closed-vocab guarantee, so we treat the manifest as untrustworthy
    (return False → the reader SKIPs). This backstops the provenance / collision
    fixes against a hand-edited / stale / older-collector artifact whose enums or
    shape drifted."""
    try:
        import jsonschema  # noqa: PLC0415 — compliance dep; lazy so light importers stay cheap

        schema = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
        return not list(jsonschema.Draft202012Validator(schema).iter_errors(data))
    except Exception:  # noqa: BLE001 — any failure → not-validated → fail-closed
        return False


def manifest_present(project_root: Path) -> bool:
    """True when the committed manifest FILE exists (regardless of whether it validates).

    Lets a consumer distinguish a PRESENT-but-untrusted (schema-invalid) manifest — where a
    fail-closed SKIP / fallback could mask a real regression — from a genuinely absent one
    (expected pre-TT8), so the untrusted case can be surfaced (FIX 3)."""
    return (Path(project_root) / _MANIFEST_REL).exists()


def load_manifest(project_root: Path) -> dict | None:
    """Read + schema-validate the committed v2 manifest. ``None`` on ANY failure.

    ``None`` drives a SKIP upstream — a missing/untrusted proof is never a pass. The
    committed manifest is derived / RTM-visibility only (R3); the detective validates it
    on READ so it inherits the collector's closed-vocab guarantee rather than trusting a
    hand-edited spec_hash/enums (the doubt-review fail-closed read)."""
    path = Path(project_root) / _MANIFEST_REL
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict) or data.get("schema_version") != 2:
        return None
    if not isinstance(data.get("requirements"), dict):
        return None
    if not _schema_valid(data):
        return None
    return data


def collision_ids(reqs: dict) -> set[str]:
    """Display ids shared by ≥2 requirement nodes across namespaces — counting BOTH
    ``active`` AND ``removed`` occurrences (MUST-FIX 2a).

    Counting only active nodes was a false-green: a display id that is ACTIVE in ns-A and
    REMOVED in ns-B is not a same-namespace duplicate, but the collector still fans a bare
    ``@FR-03.01`` tag into the active A node, so A's ``coverage=ok`` may be credited via a
    tag that actually belongs to B's removed FR. Any cross-namespace share (active or
    removed) is therefore ambiguous and must not silently credit coverage."""
    seen: dict[str, int] = {}
    for node in reqs.values():
        disp = node.get("id")
        if disp is None:
            continue
        seen[disp] = seen.get(disp, 0) + 1
    return {i for i, n in seen.items() if n > 1}


def fanned_possible_orphans(manifest: dict) -> list[dict]:
    """The tests whose coverage was credited to a collision display id — each is a
    *possible* orphan (MUST-FIX 2a): a bare tag on an ambiguous id may exercise a
    different namespace's (removed) FR. Deduped by ``(test, fr)``."""
    reqs = manifest.get("requirements") or {}
    collisions = collision_ids(reqs)
    out: list[dict] = []
    seen: set[tuple] = set()
    for node in reqs.values():
        if node.get("status") != "active":
            continue
        disp = node.get("id")
        if disp not in collisions:
            continue
        for links in (node.get("tests") or {}).values():
            for link in links or []:
                test = link.get("path") or link.get("id") or "?"
                key = (test, disp)
                if key in seen:
                    continue
                seen.add(key)
                out.append({
                    "test": test, "tagged_fr": disp,
                    "reason": "ambiguous_fanout", "category": "possible_orphan",
                })
    return out


__all__ = ["load_manifest", "collision_ids", "fanned_possible_orphans"]
