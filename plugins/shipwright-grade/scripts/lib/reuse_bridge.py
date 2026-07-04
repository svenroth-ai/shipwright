"""reuse_bridge — import the compliance + shared helpers G2 reuses (ADR-045).

The security/dependency signals reuse battle-tested code rather than re-deriving
severity buckets or license classification:

- ``collectors.collect_dependencies`` + ``sbom_render`` (license classification)
  and ``ci_security`` (severity summary + the *never-a-false-CRITICAL* grade
  guard) live in **shipwright-compliance** and import via absolute
  ``scripts.lib.*`` — so the compliance plugin root goes on ``sys.path`` and they
  import normally (mirrors :mod:`engine_bridge`).
- ``security_findings._findings_from_sarif`` (suppression-aware SARIF parse)
  lives in **shared/scripts** as a bare top-level module.

Every loader is **lazy + cached**: a run that never grades deps/security never
pays the import, and no eager ``scripts.lib`` binding shadows a sibling plugin's
own namespace in a combined pytest run (the ADR-045 collision the engine bridge
already documents). Bare grader modules are never imported as ``scripts.lib.*``.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Callable

from engine_bridge import compliance_plugin_root

_ENV_SHARED_ROOT = "SHIPWRIGHT_GRADE_SHARED_ROOT"

_CACHE: dict[str, Any] = {}


class ReuseUnavailableError(RuntimeError):
    """A reused compliance/shared helper could not be located/imported."""


def _shared_scripts_root() -> Path | None:
    """Locate ``shared/scripts`` (monorepo layout or env override)."""
    override = os.environ.get(_ENV_SHARED_ROOT)
    if override:
        cand = Path(override)
        return cand if (cand / "security_findings.py").is_file() else None
    # plugins/shipwright-grade/scripts/lib/reuse_bridge.py -> repo root.
    repo_root = Path(__file__).resolve().parents[4]
    cand = repo_root / "shared" / "scripts"
    return cand if (cand / "security_findings.py").is_file() else None


def _ensure_compliance_on_path() -> None:
    root = compliance_plugin_root()
    if root is None:
        raise ReuseUnavailableError(
            "could not locate shipwright-compliance (set "
            "SHIPWRIGHT_GRADE_COMPLIANCE_ROOT to its plugin root)")
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))


def _cached(key: str, factory: Callable[[], Any]) -> Any:
    if key not in _CACHE:
        _CACHE[key] = factory()
    return _CACHE[key]


def load_collect_dependencies() -> Callable[[Path], list]:
    """``collectors.collect_dependencies`` — lockfile/manifest → deps + licenses."""
    def _factory():
        _ensure_compliance_on_path()
        from scripts.lib.collectors import collect_dependencies  # type: ignore
        return collect_dependencies
    return _cached("collect_dependencies", _factory)


def load_license_classifier() -> tuple[Callable, Callable]:
    """``sbom_render`` ``(_classify, is_copyleft)`` — the SBOM license partition."""
    def _factory():
        _ensure_compliance_on_path()
        from scripts.lib.sbom_render import _classify, is_copyleft  # type: ignore
        return (_classify, is_copyleft)
    return _cached("license_classifier", _factory)


def load_security_grade() -> tuple[Callable, Callable]:
    """``ci_security`` ``(summarize_ci_security, grade_security_signal)``."""
    def _factory():
        _ensure_compliance_on_path()
        from scripts.lib.ci_security import (  # type: ignore
            grade_security_signal,
            summarize_ci_security,
        )
        return (summarize_ci_security, grade_security_signal)
    return _cached("security_grade", _factory)


def load_findings_from_sarif() -> Callable[[Path], list | None]:
    """``security_findings._findings_from_sarif`` — suppression-aware SARIF parse."""
    def _factory():
        root = _shared_scripts_root()
        if root is None:
            raise ReuseUnavailableError(
                "could not locate shared/scripts/security_findings.py (set "
                "SHIPWRIGHT_GRADE_SHARED_ROOT)")
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
        from security_findings import _findings_from_sarif  # type: ignore
        return _findings_from_sarif
    return _cached("findings_from_sarif", _factory)
