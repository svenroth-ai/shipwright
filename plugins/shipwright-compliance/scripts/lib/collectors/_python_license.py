"""Python license resolution from per-manifest .venv dist-info METADATA.

Pure helpers split out of ``sbom.py`` to keep the SBOM orchestrator
under the 300-LOC budget. Public surface: ``detect_python_license``,
``parse_pyproject_deps``.

Pinned to authoritative on-disk metadata (NOT ambient ``sys.path`` via
``importlib.metadata``) so output is deterministic and isolated per
manifest. See ADR-056 follow-up.

Iterate Campaign B (B2): split out of ``data_collector.py``.
"""

from __future__ import annotations

import re
from email.parser import HeaderParser as _HeaderParser
from pathlib import Path

from ._license_const import NOT_INSTALLED, UNKNOWN_LICENSE
from ._types import DependencyInfo


def _canonical_pkg_name(name: str) -> str:
    """PEP 503 canonical name: lowercase + `[-_.]+` runs → single `-`.

    Used to compare a query name against a dist-info dir's project
    stem regardless of how either side spells separators / case.
    `Foo_Bar-1.0.0.dist-info`, `foo.bar`, `FOO-BAR` all share canonical
    `foo-bar`.
    """
    return re.sub(r"[-_.]+", "-", name).lower()


def _version_sort_key(version: str) -> tuple:
    """Sort key for distribution versions. Prefers `packaging.version.Version`
    when available (PEP 440-aware); falls back to a tuple of integer
    components + the raw string when not.

    Returns a 2-tuple ``(sortable, raw)`` so equal sortables fall back to
    stable lexicographic order. Robust against weird version strings —
    unparseable versions sort before parseable ones (PEP 440 invalid →
    raw string).
    """
    try:
        from packaging.version import InvalidVersion, Version  # noqa: PLC0415
    except ImportError:
        Version = None  # type: ignore[assignment]
        InvalidVersion = Exception  # type: ignore[assignment]

    if Version is not None:
        try:
            return (1, Version(version), version)
        except InvalidVersion:
            pass
    # Fallback: integer-by-integer tuple. `10` > `2` numerically.
    parts: list = []
    for chunk in version.split("."):
        try:
            parts.append((1, int(chunk)))
        except ValueError:
            parts.append((0, chunk))
    return (0, tuple(parts), version)


def _iter_site_packages_dirs(manifest_dir: Path):
    """Yield site-packages dirs under ``manifest_dir/.venv``, deterministically.

    Windows: ``<venv>/Lib/site-packages``.
    POSIX:   ``<venv>/lib/python*/site-packages`` (sorted by name so
    candidate enumeration is stable when multiple python-X.Y dirs exist
    in a damaged env).
    """
    venv = manifest_dir / ".venv"
    if not venv.is_dir():
        return
    win = venv / "Lib" / "site-packages"
    if win.is_dir():
        yield win
    posix_root = venv / "lib"
    if posix_root.is_dir():
        try:
            for python_dir in sorted(posix_root.iterdir(), key=lambda p: p.name):
                if python_dir.is_dir() and python_dir.name.startswith("python"):
                    sp = python_dir / "site-packages"
                    if sp.is_dir():
                        yield sp
        except OSError:
            # Defensive: unreadable lib/ should not crash SBOM generation.
            return


def _find_distinfo_candidates(
    site_packages: Path, canonical: str
) -> list[Path]:
    """Return dist-info dirs in ``site_packages`` matching ``canonical``,
    sorted by parsed version (lowest first). Caller picks ``[-1]`` for
    the highest version when multiple stale installs coexist (OpenAI
    HIGH-2 / code-review HIGH-1: must be version-aware, not lexicographic).
    """
    try:
        all_distinfos = sorted(site_packages.glob("*.dist-info"))
    except OSError:
        return []
    matches: list[tuple] = []
    for distinfo in all_distinfos:
        # dist-info dir name shape: `<project>-<version>.dist-info`.
        stem = distinfo.name[: -len(".dist-info")]
        if "-" not in stem:
            continue
        project, _, version = stem.rpartition("-")
        if _canonical_pkg_name(project) == canonical:
            matches.append((_version_sort_key(version), distinfo))
    matches.sort(key=lambda pair: pair[0])
    return [distinfo for _, distinfo in matches]


def _parse_metadata_license(distinfo: Path) -> str:
    """Parse a single dist-info METADATA file. Returns license or
    ``UNKNOWN_LICENSE``.

    Only reached when the dist-info dir EXISTS (the package is installed), so
    every non-license outcome here is ``UNKNOWN_LICENSE`` (resolved-but-no-
    declared-license), never ``NOT_INSTALLED``. All filesystem / parse errors
    are swallowed to ``UNKNOWN_LICENSE`` — SBOM generation must never crash
    because one METADATA file is unreadable. Output is always single-line.
    """
    metadata_path = distinfo / "METADATA"
    try:
        # Explicit utf-8 (Gemini MEDIUM-3): METADATA on Windows must NOT
        # fall through to the cp1252 default.
        raw = metadata_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return UNKNOWN_LICENSE

    try:
        msg = _HeaderParser().parsestr(raw)
    except Exception:  # noqa: BLE001
        return UNKNOWN_LICENSE

    candidate = ""

    # Order: License → License-Expression (PEP 639) → Trove classifier.
    license_ = msg.get("License") or msg.get("License-Expression") or ""
    license_ = (license_ or "").strip()
    if license_ and license_ != "UNKNOWN":
        candidate = license_
    else:
        # Iterate ALL Classifier headers (Gemini MEDIUM-2: get_all, not get).
        for classifier in msg.get_all("Classifier") or []:
            if classifier.startswith("License :: "):
                # e.g. "License :: OSI Approved :: MIT License" → "MIT"
                parts = classifier.split(" :: ")
                if parts:
                    candidate = parts[-1].replace(" License", "")
                    break

    if not candidate:
        return UNKNOWN_LICENSE
    # Single-return one-line clamp (code-review M2: applies to all paths).
    return candidate.splitlines()[0].strip() or UNKNOWN_LICENSE


def detect_python_license(package_name: str, manifest_dir: Path) -> str:
    """Resolve a Python package license from a per-manifest .venv.

    Reads ``<manifest_dir>/.venv/.../site-packages/<pkg>-*.dist-info/METADATA``
    directly. See ADR-056 follow-up: deterministic + cross-manifest isolated,
    no ambient sys.path probe.

    Returns ``NOT_INSTALLED`` when no matching dist-info exists in the
    manifest's ``.venv`` (no install yet, or stale env without the dep) — a
    scan artifact, NOT a license finding. Returns ``UNKNOWN_LICENSE`` only when
    the dist-info IS present but declares no license (a genuine concern). When
    multiple dist-info dirs match the same canonicalized package name, the
    highest-versioned directory wins by semver-aware sort.
    """
    canonical = _canonical_pkg_name(package_name)
    for site_packages in _iter_site_packages_dirs(manifest_dir):
        matches = _find_distinfo_candidates(site_packages, canonical)
        if not matches:
            continue
        # Highest version last in sorted list → pick it (OpenAI HIGH-2).
        chosen = matches[-1]
        return _parse_metadata_license(chosen)
    return NOT_INSTALLED


def parse_pyproject_dep_specs(pyproject_path: Path) -> list[tuple[str, str, str]]:
    """Parse ``(name, version_floor_or_"any", dep_type)`` triples from a
    pyproject.toml WITHOUT resolving licenses. The SBOM-inventory path resolves
    the installed version (lockfile) + license (global venv scan) itself; this
    keeps the text parse in one place. Pure parse, single manifest read."""
    specs: list[tuple[str, str, str]] = []
    content = pyproject_path.read_text(encoding="utf-8")

    in_deps = False
    in_dev = False
    for line in content.splitlines():
        stripped = line.strip()
        if stripped == "dependencies = [":
            in_deps, in_dev = True, False
            continue
        if "dev" in stripped and "= [" in stripped:
            in_deps, in_dev = True, True
            continue
        if in_deps and stripped == "]":
            in_deps = False
            continue
        if in_deps and stripped.startswith('"'):
            dep_str = stripped.strip('",')
            match = re.match(r"^([a-zA-Z0-9_.-]+)(?:[><=!~]+(.+))?$", dep_str)
            if match:
                specs.append((
                    match.group(1),
                    match.group(2) or "any",
                    "dev" if in_dev else "runtime",
                ))
    return specs


def parse_pyproject_deps(pyproject_path: Path) -> list[DependencyInfo]:
    """Parse dependencies + resolve each license from the manifest-local .venv
    dist-info METADATA (per-manifest; NOT ambient sys.path).

    Used by the **triage producer**, which keeps strict per-manifest
    NOT_INSTALLED-vs-UNKNOWN semantics. The SBOM-inventory path uses
    ``parse_pyproject_dep_specs`` + lockfile/global-venv resolution instead.
    """
    manifest_dir = pyproject_path.parent
    return [
        DependencyInfo(
            name=name,
            version=floor,
            dep_type=dep_type,
            license=detect_python_license(name, manifest_dir),
        )
        for name, floor, dep_type in parse_pyproject_dep_specs(pyproject_path)
    ]
