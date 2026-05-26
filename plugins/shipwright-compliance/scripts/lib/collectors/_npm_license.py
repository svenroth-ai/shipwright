"""NPM license resolution helpers — lockfile-first, node_modules fallback.

Pure helpers split out of ``sbom.py`` to keep the SBOM orchestrator
under the 300-LOC budget. Public surface: ``detect_npm_license``.

Iterate Campaign B (B2): split out of ``data_collector.py``.
"""

from __future__ import annotations

import json
from pathlib import Path


def _read_npm_lockfile_licenses(manifest_dir: Path) -> dict[str, str]:
    """Parse package-lock.json (lockfileVersion 3) and return {name: license}.

    lockfileVersion 3 stores entries under `packages` keyed by path
    (e.g. `"node_modules/foo"`); each entry may carry a `license` field.
    Returns an empty dict if the lockfile is absent / unparseable.
    """
    lock_path = manifest_dir / "package-lock.json"
    if not lock_path.exists():
        return {}
    try:
        data = json.loads(lock_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    result: dict[str, str] = {}
    for path_key, entry in data.get("packages", {}).items():
        if not isinstance(entry, dict):
            continue
        # path_key is "" for the root project, or "node_modules/<name>" for deps.
        if not path_key.startswith("node_modules/"):
            continue
        name = path_key[len("node_modules/"):]
        license_ = entry.get("license")
        if isinstance(license_, str):
            result[name] = license_
        elif isinstance(license_, dict) and isinstance(license_.get("type"), str):
            result[name] = license_["type"]
    return result


def detect_npm_license(manifest_dir: Path, package_name: str) -> str:
    """Resolve a JS package license — lockfile-first, node_modules fallback.

    Phase 0f: prefer package-lock.json (centralized + works without `npm
    install`); fall back to node_modules/<pkg>/package.json (legacy path).
    """
    lockfile_licenses = _read_npm_lockfile_licenses(manifest_dir)
    if package_name in lockfile_licenses:
        return lockfile_licenses[package_name]
    pkg_json = manifest_dir / "node_modules" / package_name / "package.json"
    if pkg_json.exists():
        try:
            data = json.loads(pkg_json.read_text(encoding="utf-8"))
            license_ = data.get("license", "unknown")
            if isinstance(license_, dict):
                license_ = license_.get("type", "unknown")
            return license_
        except (json.JSONDecodeError, OSError):
            pass
    return "unknown"
