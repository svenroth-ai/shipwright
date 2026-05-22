"""Adapter layer between iterate-12 verifiers and the detective audit.

This module is the **single choke point** for iterate-12 import drift.
Every verifier symbol the audit depends on is named in
``REQUIRED_SYMBOLS`` below; the ``verify_imports()`` gate is called once
at the start of every audit run and fails fast with a single clear
message on rename / removal / signature drift.

Also owns the ``CheckResult → Finding`` translation with ``source`` tagging
(``preventive-rerun`` for iterate-12 re-runs, ``detective-only`` for audit-
native checks) — plan v7 Option Z § Architecture.
"""

from __future__ import annotations

import importlib
import importlib.util
import inspect
import sys
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any, Callable

# Ensure ``shared/scripts`` is on sys.path BEFORE importing anything from
# the verifier package. Mirrors plugins/shipwright-run/scripts/lib/
# phase_validators.py but is defensive against a common test-ordering
# pitfall: ``plugins/shipwright-compliance/scripts`` also has a
# ``tools/`` subpackage (the compliance plugin's own tools), so if that
# path ends up at sys.path[0] first, ``from tools.verifiers import X``
# resolves into the compliance plugin's ``tools`` (which has no
# ``verifiers`` submodule) and fails with a confusing "No module named
# 'tools.verifiers'" error. We fix this by (a) inserting shared/scripts
# at position 0 and (b) evicting any already-cached ``tools`` module
# that doesn't come from shared/scripts.
_PLUGIN_ROOT = Path(__file__).resolve().parent.parent.parent
_SHARED_SCRIPTS = _PLUGIN_ROOT.parent.parent / "shared" / "scripts"
_shared_scripts_str = str(_SHARED_SCRIPTS)
if _shared_scripts_str in sys.path:
    sys.path.remove(_shared_scripts_str)
sys.path.insert(0, _shared_scripts_str)

# Evict any ``tools`` package that was imported from a non-shared path
# (see comment above). ``tools.verifiers.*`` re-imports will then resolve
# cleanly against shared/scripts.
_stale_tools = sys.modules.get("tools")
if _stale_tools is not None:
    _tools_file = getattr(_stale_tools, "__file__", "") or ""
    _tools_path = getattr(_stale_tools, "__path__", None)
    if _tools_path is not None:
        _expected = str(_SHARED_SCRIPTS / "tools")
        # ``_tools_path`` is a list (or _NamespacePath) of strings.
        if not any(_expected in p for p in _tools_path):
            for _k in [k for k in sys.modules if k == "tools" or k.startswith("tools.")]:
                sys.modules.pop(_k, None)


# ---------------------------------------------------------------------------
# Required-symbol registry (iterate-12 + PR 4 imports)
#
# Tuple order: (module, symbol, min_arity). ``min_arity`` is how many
# positional args the function must accept — used by the version gate to
# catch signature drift, not just rename drift. ``0`` means "any arity"
# (used for type imports like ``CheckResult``).
# ---------------------------------------------------------------------------

REQUIRED_SYMBOLS: list[tuple[str, str, int]] = [
    # Group C imports (plan_checks / design_checks)
    ("tools.verifiers.plan_checks", "check_fr_orphans_in_plan", 1),
    ("tools.verifiers.plan_checks", "check_section_files_match_manifest", 1),
    ("tools.verifiers.plan_checks", "check_section_id_validity", 1),
    ("tools.verifiers.design_checks", "check_design_fr_coverage", 1),
    # Group B3/B6 imports (build_checks)
    ("tools.verifiers.build_checks", "check_build_test_files_exist", 1),
    ("tools.verifiers.build_checks", "check_commit_sha_in_git", 1),
    # Group F imports (common)
    ("tools.verifiers.common", "check_adr_ids_sequential", 1),
    ("tools.verifiers.common", "check_adr_status_valid", 1),
    ("tools.verifiers.common", "check_adr_supersession_exists", 1),
    # Shared types
    ("tools.verifiers.common", "CheckResult", 0),
    ("tools.verifiers.common", "Severity", 0),
]


class ImportGateError(RuntimeError):
    """Raised when iterate-12 imports are drifting (rename / removal / arity)."""


def _ensure_shared_scripts_first() -> None:
    """Defensively put ``shared/scripts`` at sys.path[0] + evict stale ``tools``.

    The same logic runs at module-import time, but later test files (e.g.
    ``test_enforcement_hooks.py``) ``sys.path.insert(0, ...)`` the
    compliance plugin's ``scripts/`` directory, and pytest's own
    ``rootdir_fallback`` + ``conftest`` walker can pre-cache ``tools`` as
    the compliance plugin's regular package before we get a chance to
    act. Re-applying the fix here means ``verify_imports`` is robust
    against whatever path/cache state the caller inherited.

    The eviction is unconditional: if ANY ``tools`` module is cached
    whose ``__path__`` doesn't include ``shared/scripts/tools``, blow it
    away so the next ``import tools.verifiers.X`` walks sys.path afresh.
    """
    # Step 1: put shared/scripts at position 0.
    s = str(_SHARED_SCRIPTS)
    if s in sys.path:
        sys.path.remove(s)
    sys.path.insert(0, s)

    # Step 2: evict any cached top-level package that doesn't resolve
    # against shared/scripts. Both ``tools`` and ``lib`` exist as regular
    # packages in both shared/scripts and the compliance plugin's
    # scripts/; whichever is imported first wins the sys.modules slot,
    # and later calls look up submodules there regardless of sys.path
    # order. Cache eviction is the only reliable cross-order fix.
    for pkg_name in ("tools", "lib"):
        expected = str(_SHARED_SCRIPTS / pkg_name)
        stale = sys.modules.get(pkg_name)
        if stale is None:
            continue
        pkg_path = getattr(stale, "__path__", None)
        if pkg_path is not None and any(expected in p for p in pkg_path):
            continue  # already pointing at shared/scripts
        for k in [k for k in sys.modules
                  if k == pkg_name or k.startswith(pkg_name + ".")]:
            sys.modules.pop(k, None)


def verify_imports(symbols: list[tuple[str, str, int]] | None = None) -> None:
    """Fail fast if any required iterate-12 symbol is missing or reshaped.

    Runs at the top of ``run_audit.py``. Failures here mean the plan's
    Critical-Files section is outdated and the audit would silently drop
    C/F/B3/B6 coverage. One message names every drifting symbol at once
    so the operator doesn't have to re-run the audit N times to discover
    N missing imports.
    """
    _ensure_shared_scripts_first()
    symbols = symbols or REQUIRED_SYMBOLS
    errors: list[str] = []

    for module_path, symbol, min_arity in symbols:
        try:
            # nosemgrep: python.lang.security.audit.non-literal-import.non-literal-import
            # `module_path` comes from the hardcoded REQUIRED_SYMBOLS constant (no user input).
            mod = importlib.import_module(module_path)
        except ImportError as exc:
            errors.append(f"{module_path}: module not importable ({exc})")
            continue
        obj = getattr(mod, symbol, None)
        if obj is None:
            errors.append(f"{module_path}.{symbol}: missing")
            continue
        if min_arity > 0:
            try:
                sig = inspect.signature(obj)
            except (TypeError, ValueError) as exc:
                errors.append(f"{module_path}.{symbol}: uninspectable ({exc})")
                continue
            positional = [
                p for p in sig.parameters.values()
                if p.kind in (inspect.Parameter.POSITIONAL_ONLY,
                              inspect.Parameter.POSITIONAL_OR_KEYWORD)
            ]
            if len(positional) < min_arity:
                errors.append(
                    f"{module_path}.{symbol}: expected >={min_arity} positional "
                    f"args, got {len(positional)}",
                )

    if errors:
        raise ImportGateError(
            "iterate-12 import drift (plan v7 audit requires these symbols):\n"
            + "\n".join(f"  - {e}" for e in errors)
        )


# ---------------------------------------------------------------------------
# Finding schema — distinct from CheckResult, carries audit-specific fields
# ---------------------------------------------------------------------------

# Valid ``source`` values. Keep the set small and explicit — new sources
# should go through a plan change, not a silent string literal.
SOURCE_DETECTIVE_ONLY = "detective-only"
SOURCE_PREVENTIVE_RERUN = "preventive-rerun"
_VALID_SOURCES = frozenset({SOURCE_DETECTIVE_ONLY, SOURCE_PREVENTIVE_RERUN})


@dataclass
class Finding:
    """One audit finding.

    Shaped for the audit Markdown + JSON report. Distinct from
    Phase-Quality's finding schema (``status: PASS/FAIL/WARN/SKIP``) on
    purpose — the two layers should be diffable, not mistakable.
    """

    group: str  # "A" | "B" | "C" | "D" | "E" | "F" | "G"
    check_id: str  # e.g. "A2", "B7", "E1"
    name: str  # short human-readable handle
    severity: str  # "HIGH" | "MEDIUM" | "LOW"
    source: str  # detective-only | preventive-rerun
    status: str  # "fail" | "pass" | "skip"
    detail: str = ""
    suggested_iterate_cmd: str | None = None
    evidence: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.source not in _VALID_SOURCES:
            raise ValueError(
                f"Finding.source must be one of {_VALID_SOURCES!r}, got {self.source!r}"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "group": self.group, "check_id": self.check_id, "name": self.name,
            "severity": self.severity, "source": self.source,
            "status": self.status, "detail": self.detail,
            "suggested_iterate_cmd": self.suggested_iterate_cmd,
            "evidence": list(self.evidence),
        }


def check_result_to_finding(
    result: Any,  # CheckResult, typed loosely so import drift doesn't crash
    *,
    group: str,
    check_id: str,
    source: str,
    severity_override: str | None = None,
    suggested_iterate_cmd: str | None = None,
) -> Finding:
    """Translate an iterate-12 ``CheckResult`` into an audit ``Finding``.

    Mapping:
    - ``ok is True``  → status="pass"
    - ``ok is None``  → status="skip"
    - ``ok is False`` → status="fail"
    - CheckResult.severity (error/warning/skipped) maps to HIGH/MEDIUM/skip
      unless ``severity_override`` is set.
    """
    ok = getattr(result, "ok", None)
    status = "pass" if ok is True else ("skip" if ok is None else "fail")
    raw_sev = getattr(result, "severity", "error")
    severity = severity_override or {
        "error": "HIGH", "warning": "MEDIUM", "skipped": "LOW",
    }.get(str(raw_sev), "HIGH")
    detail = getattr(result, "detail", "") or ""

    return Finding(
        group=group, check_id=check_id,
        name=getattr(result, "name", check_id),
        severity=severity, source=source, status=status,
        detail=detail,
        suggested_iterate_cmd=suggested_iterate_cmd,
    )


# ---------------------------------------------------------------------------
# Convenience: importer for the iterate-12 checks
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Pollution-free loader for shared/scripts/lib parsers (Step 4 — Group A/D)
# ---------------------------------------------------------------------------

_LOADED_SHARED_LIBS: dict[str, ModuleType] = {}


def load_shared_lib(module_name: str) -> ModuleType:
    """Load ``shared/scripts/lib/<module_name>.py`` without polluting ``lib`` in
    ``sys.modules``.

    Group A and Group D both want ``drift_parsers`` from shared, but a plain
    ``from lib import drift_parsers`` caches the ``lib`` package as
    ``shared/scripts/lib`` for the rest of the test session — which then
    shadows the compliance plugin's own ``lib`` package (where
    ``thresholds.py`` lives) and breaks ``test_enforcement_hooks``.

    Loading via ``importlib.util.spec_from_file_location`` under a unique
    module name avoids the ``lib`` namespace entirely. Cached per module
    name across calls.
    """
    cached = _LOADED_SHARED_LIBS.get(module_name)
    if cached is not None:
        return cached

    file_path = _SHARED_SCRIPTS / "lib" / f"{module_name}.py"
    if not file_path.is_file():
        raise ImportError(f"shared lib module not found: {file_path}")

    sentinel = f"_shipwright_compliance_audit_{module_name}"
    spec = importlib.util.spec_from_file_location(sentinel, file_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"could not load spec for {file_path}")
    module = importlib.util.module_from_spec(spec)
    # Register in sys.modules BEFORE exec_module so dataclasses defined
    # inside the loaded module can resolve their own __module__ via
    # ``sys.modules[cls.__module__]`` — Python's stdlib ``dataclasses``
    # does this lookup at class-creation time.
    sys.modules[sentinel] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(sentinel, None)
        raise
    _LOADED_SHARED_LIBS[module_name] = module
    return module


def import_iterate12_checks() -> dict[str, Callable[..., Any]]:
    """Return the iterate-12 check callables by short name.

    Runs ``verify_imports()`` first so we never return a partially-populated
    dict. Call this once per audit run and cache the result.
    """
    _ensure_shared_scripts_first()
    verify_imports()

    from tools.verifiers.build_checks import (  # type: ignore  # noqa: E402
        check_build_test_files_exist, check_commit_sha_in_git,
    )
    from tools.verifiers.common import (  # type: ignore  # noqa: E402
        check_adr_ids_sequential, check_adr_status_valid,
        check_adr_supersession_exists,
    )
    from tools.verifiers.design_checks import (  # type: ignore  # noqa: E402
        check_design_fr_coverage,
    )
    from tools.verifiers.plan_checks import (  # type: ignore  # noqa: E402
        check_fr_orphans_in_plan, check_section_files_match_manifest,
        check_section_id_validity,
    )

    return {
        # plan
        "check_fr_orphans_in_plan": check_fr_orphans_in_plan,
        "check_section_files_match_manifest": check_section_files_match_manifest,
        "check_section_id_validity": check_section_id_validity,
        # design
        "check_design_fr_coverage": check_design_fr_coverage,
        # build
        "check_build_test_files_exist": check_build_test_files_exist,
        "check_commit_sha_in_git": check_commit_sha_in_git,
        # ADR
        "check_adr_ids_sequential": check_adr_ids_sequential,
        "check_adr_status_valid": check_adr_status_valid,
        "check_adr_supersession_exists": check_adr_supersession_exists,
    }
