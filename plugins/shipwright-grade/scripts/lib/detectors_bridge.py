"""detectors_bridge — reuse the /shipwright-adopt detectors by IMPORT (not fork).

The adopt plugin already ships deterministic, read-only detectors for stack,
test frameworks, feature/route inference and CI presence. We import them rather
than re-implement, so the grader's structural signals stay identical to what
adoption sees.

Reused-collector audit (Gemini #5 / GPT #14 — the untrusted-input track). Each
imported module was read and confirmed to be:

- **read-only** — only ``Path.read_text`` / ``Path.glob`` / ``rglob`` / ``.exists``
  and (in ``stack_detector``) list-arg reads; no writes, no ``os.system``, no
  ``subprocess`` package-manager execution, no shell interpolation;
- **no package-manager execution** — none of ``npm``/``pip``/``uv``/``go``/
  ``cargo`` is ever invoked; manifests are parsed as text/JSON, never run;
- **symlink-escape** — the adopt detectors read only files under the passed
  ``project_root`` via ``glob``/``rglob``; the grader additionally bounds
  traversal in ``repo_context`` (within-root, no symlink-following).

Every call is wrapped so a detector raising on a hostile repo degrades to a safe
empty default (the projector then renders the corresponding dimension ``n/a``),
never a crash.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

_ENV_ADOPT_ROOT = "SHIPWRIGHT_GRADE_ADOPT_ROOT"

# Top-level directories excluded from feature/stack inference so vendored /
# generated code does not pollute the requirement-traceability signal. The
# adopt detectors match these as relative-path prefixes.
_DEFAULT_EXCLUDES = frozenset({
    "node_modules", "vendor", "third_party", "third-party", "dist", "build",
    ".venv", "venv", "examples", "example", ".git", "target", "out",
})


def _adopt_lib_dir() -> Path | None:
    """Locate the adopt plugin's ``scripts/lib`` (monorepo sibling or env override)."""
    override = os.environ.get(_ENV_ADOPT_ROOT)
    if override:
        cand = Path(override) / "scripts" / "lib"
        return cand if cand.is_dir() else None
    # plugins/shipwright-grade/scripts/lib/detectors_bridge.py -> plugins/
    plugins_dir = Path(__file__).resolve().parents[3]
    cand = plugins_dir / "shipwright-adopt" / "scripts" / "lib"
    return cand if cand.is_dir() else None


def _load_detectors() -> dict[str, Any]:
    """Import the adopt detectors bare (their lib dir on ``sys.path``)."""
    lib_dir = _adopt_lib_dir()
    if lib_dir is None:
        return {}
    if str(lib_dir) not in sys.path:
        sys.path.insert(0, str(lib_dir))
    fns: dict[str, Any] = {}
    try:
        from stack_detector import detect_stack  # type: ignore
        fns["detect_stack"] = detect_stack
    except ImportError:
        pass
    try:
        from test_framework_detector import detect_test_frameworks  # type: ignore
        fns["detect_test_frameworks"] = detect_test_frameworks
    except ImportError:
        pass
    try:
        from feature_inferrer import infer_features_ast  # type: ignore
        fns["infer_features_ast"] = infer_features_ast
    except ImportError:
        pass
    try:
        from ci_detector import detect_ci  # type: ignore
        fns["detect_ci"] = detect_ci
    except ImportError:
        pass
    return fns


def detect_all(root: Path, excludes: set[str] | None = None) -> dict[str, Any]:
    """Run every available detector against ``root``; degrade safely on failure.

    Returns a dict with keys ``stack``, ``test_frameworks``, ``features``,
    ``ci`` — each an empty/neutral default when the detector is unavailable or
    raises on a hostile repo. ``features`` is sorted by a stable key so the
    feature ordering (and any downstream truncation) is deterministic.
    """
    excludes = set(excludes) if excludes else set(_DEFAULT_EXCLUDES)
    fns = _load_detectors()

    stack: dict[str, Any] = {"primary_language": "unknown"}
    if "detect_stack" in fns:
        try:
            stack = fns["detect_stack"](root, excludes) or stack
        except Exception:
            pass

    test_frameworks: dict[str, Any] = {}
    if "detect_test_frameworks" in fns:
        try:
            test_frameworks = fns["detect_test_frameworks"](root) or {}
        except Exception:
            test_frameworks = {}

    features: list[dict[str, Any]] = []
    if "infer_features_ast" in fns:
        try:
            features = fns["infer_features_ast"](root, stack, excludes) or []
        except Exception:
            features = []
    # Deterministic ordering — the reused detector yields filesystem order.
    features.sort(key=lambda f: (str(f.get("source_file", "")),
                                 str(f.get("route", "")),
                                 str(f.get("framework", ""))))

    ci: dict[str, Any] = {"provider": None, "workflows": []}
    if "detect_ci" in fns:
        try:
            ci = fns["detect_ci"](root) or ci
        except Exception:
            ci = {"provider": None, "workflows": []}

    return {
        "stack": stack,
        "test_frameworks": test_frameworks,
        "features": features,
        "ci": ci,
    }
