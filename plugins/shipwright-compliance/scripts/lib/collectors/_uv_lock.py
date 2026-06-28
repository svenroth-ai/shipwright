"""Resolve installed package versions from a ``uv.lock`` lockfile.

A ``pyproject.toml`` only carries a specifier *floor* (``openai>=1.0.0``);
``uv.lock`` carries the **resolved / installed** version. The SBOM must show
and dedupe by the installed version (AR-04 — otherwise the same package
declared at different floors in two manifests renders as two rows), so we read
it from the manifest's sibling lockfile.

``uv.lock`` does NOT record license metadata — license resolution stays in
``_python_license.py`` (dist-info ``METADATA``). This module is version-only.

Iterate 2026-06-28 (AR-04 SBOM data quality).
"""

from __future__ import annotations

import tomllib
from pathlib import Path

from ._python_license import _canonical_pkg_name


def load_lock_versions(manifest_dir: Path) -> dict[str, str]:
    """Return ``{canonical_name: resolved_version}`` from ``manifest_dir/uv.lock``.

    Keys are PEP 503 canonicalized so a manifest spelling (``google-genai``)
    matches the lock's project name (``google-genai`` / ``google_genai``).
    A missing or malformed lockfile yields ``{}`` (the caller falls back to the
    pyproject specifier floor) — SBOM generation must never crash on a bad lock.
    """
    lock_path = manifest_dir / "uv.lock"
    try:
        data = tomllib.loads(lock_path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError, ValueError):
        return {}

    versions: dict[str, str] = {}
    packages = data.get("package")
    if not isinstance(packages, list):
        return {}
    for pkg in packages:
        if not isinstance(pkg, dict):
            continue
        name = pkg.get("name")
        version = pkg.get("version")
        if isinstance(name, str) and isinstance(version, str):
            versions[_canonical_pkg_name(name)] = version
    return versions
